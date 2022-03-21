import asyncio
import json
import random
import textwrap
import time
from datetime import datetime
from io import BytesIO
from itertools import cycle, islice

import discord
from captcha.image import ImageCaptcha
from discord.commands import SlashCommandGroup
from discord.ext import commands, tasks
from discord.utils import escape_markdown
from humanfriendly import format_timespan

import icons
import word_list
from constants import (
    CAPTCHA_INTERVAL,
    MAX_RACE_JOIN,
    RACE_EXPIRE_TIME,
    SUPPORT_SERVER_INVITE,
    TEST_RANGE,
)
from helpers.checks import cooldown
from helpers.converters import quote_amt, word_amt
from helpers.image import get_base, get_loading_img, get_width_height, wrap_text
from helpers.ui import BaseView
from helpers.user import get_pacer_display, get_pacer_type_name
from helpers.utils import cmd_run_before, get_test_stats


def load_test_file(name):
    with open(f"./word_list/{name}", "r") as f:
        return json.load(f)


def get_test_zone(cw):
    if cw in range(10, 21):
        return "short", "(10-20) words"

    elif cw in range(21, 50):
        return "medium", "(21-50) words"

    elif cw in range(51, 100):
        return "long", "(51-100) words"

    return None


class TestResultView(BaseView):
    def __init__(self, ctx, user, is_dict, quote, length):
        super().__init__(ctx)

        # Adding link buttons because they can't be added with a decorator
        self.add_item(
            discord.ui.Button(label="Community Server", url=SUPPORT_SERVER_INVITE)
        )
        self.add_item(
            discord.ui.Button(label="Invite Bot", url=ctx.bot.create_invite_link())
        )

        # Settings of the test completed
        self.length = length
        self.is_dict = is_dict
        self.quote = quote

        self.user = user

    @discord.ui.button(label="Next Test", style=discord.ButtonStyle.primary)
    async def next_test(self, button, interaction):
        if self.is_dict:
            quote = await Typing.handle_dictionary_input(self.ctx, self.length)
        else:
            quote = await Typing.handle_quote_input(self.length)

        await Typing.do_typing_test(
            self.ctx,
            self.is_dict,
            quote,
            self.length,
            interaction.response.send_message,
        )

    @discord.ui.button(label="Practice Test", style=discord.ButtonStyle.primary)
    async def practice_test(self, button, interaction):
        message, end_time, pacer_name, raw_quote = await Typing.personal_test_input(
            self.user, self.ctx, 2, self.quote, interaction.response.send_message
        )

        u_input = message.content.split()

        wpm, raw, acc, cc, cw, word_history = get_test_stats(
            u_input, self.quote, end_time
        )

        ts = "\N{THIN SPACE}"

        # Sending the results
        # Spacing in title keeps same spacing if word history is short
        embed = self.ctx.embed(
            title=f"Practice Test Results (Repeat){ts*75}\n\n`Statistics`",
        )

        embed.set_author(
            name=self.ctx.author,
            icon_url=self.ctx.author.display_avatar.url,
        )

        embed.set_thumbnail(url="https://i.imgur.com/l9sLfQx.png")

        # Statistics

        space = " "

        embed.add_field(name=":person_walking: Wpm", value=wpm)

        embed.add_field(name=":person_running: Raw Wpm", value=raw)

        embed.add_field(name=":dart: Accuracy", value=f"{acc}%")

        embed.add_field(name=":clock1: Time", value=f"{end_time}s")

        embed.add_field(name=f":x: Mistakes", value=len(u_input) - cw)

        embed.add_field(name="** **", value="** **")

        embed.add_field(
            name="** **",
            value=f"**Word History**\n> {word_history}\n\n```ini\n{space*13}[ Test Settings ]```\n** **",
            inline=False,
        )

        # Settings
        embed.add_field(
            name=":earth_americas: Language", value=self.user.language.capitalize()
        )

        embed.add_field(name=":timer: Pacer", value=pacer_name)

        embed.add_field(
            name=":1234: Words", value=f"{len(self.quote)} ({len(raw_quote)} chars)"
        )

        await message.reply(embed=embed, mention_author=False)

        await self.ctx.respond("Warning: Practice tests aren't saved")


class RaceMember:
    def __init__(self, user):
        """
        user: user object
        """
        self.user = user

        # User's database document
        self.data = None

        # The test score (mongo.Score)
        self.result = None


class RaceJoinButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Join", style=discord.ButtonStyle.success)

    async def callback(self, interaction):
        await self.view.add_racer(interaction)


class RaceLeaveButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Leave", style=discord.ButtonStyle.danger)

    async def callback(self, interaction):
        await self.view.remove_racer(interaction)


class RaceJoinView(BaseView):
    def __init__(self, ctx, *test_data):
        super().__init__(ctx, timeout=None, personal=False)

        self.test_data = test_data
        self.racers = {}  # id: user object (for preserve uniqueness)

        # Cooldown for joining the race (prevents spamming join and leave)
        self.race_join_cooldown = commands.CooldownMapping.from_cooldown(
            1, 10, commands.BucketType.user
        )

    async def remove_racer(self, interaction):
        user = interaction.user

        # If the author leaves, the race is ended
        is_author = user.id == self.ctx.author.id

        msg = (
            self.ctx.interaction.message
            or await self.ctx.interaction.original_message()
        )

        if is_author:
            embed = self.ctx.error_embed(
                title=f"{icons.caution} Race Ended",
                description="The race leader left the race",
            )

            await msg.edit(embed=embed, view=None)
            return self.stop()

        if user.id not in self.racers:
            return await interaction.response.send_message(
                "You are not in the race!", ephemeral=True
            )

        del self.racers[user.id]

        embed = self.get_race_join_embed()

        await msg.edit(embed=embed, view=self)

        return await interaction.response.send_message(
            "You left the race", ephemeral=True
        )

    async def handle_race(self):
        await self.ctx.respond("race command not finished")

    async def add_racer(self, interaction):
        if len(self.racers) == MAX_RACE_JOIN:
            return

        user = interaction.user

        if user.id in self.racers:
            return await interaction.response.send_message(
                "You are already in this race!", ephemeral=True
            )

        msg = (
            self.ctx.interaction.message
            or await self.ctx.interaction.original_message()
        )

        # If the author joins, the race starts
        is_author = user.id == self.ctx.author.id

        if is_author and len(self.racers) == 0:
            return await interaction.response.send_message(
                "You cannot start this race until another user joins!", ephemeral=True
            )

        if is_author:
            if self.children:
                for child in self.children:
                    child.disabled = True

            # Starting the race
            await self.handle_race()

        else:
            bucket = self.race_join_cooldown.get_bucket(interaction.message)

            retry_after = bucket.update_rate_limit()

            if retry_after:
                timespan = format_timespan(retry_after)

                return await interaction.response.send_message(
                    f"Sorry you are being rate limited, try again in {timespan}",
                    ephemeral=True,
                )

        self.racers[user.id] = RaceMember(user)
        embed = self.get_race_join_embed(is_author)

        await msg.edit(embed=embed, view=self)

        if is_author:
            self.stop()
            await Typing.do_race(self.ctx, self.racers, *self.test_data)

        else:
            return await interaction.response.send_message(
                "You joined the race", ephemeral=True
            )

    def get_formatted_users(self):
        if len(self.racers) == 0:
            return "There are no other racers"
        raw_content = ", ".join(f"{r.user}" for r in self.racers.values())

        content = "\n".join(textwrap.wrap(text=raw_content, width=64))

        return escape_markdown(content)

    @property
    def total_racers(self):
        return len(self.racers)

    # Using a task to expire the race because the built in view timeout restarts after each interaction
    @tasks.loop(seconds=RACE_EXPIRE_TIME, count=2)
    async def timeout_race(self):
        if self.timeout_race.current_loop == 1:
            await self.send_expire_race_message()
            self.stop()

    async def send_expire_race_message(self):
        timespan = format_timespan(RACE_EXPIRE_TIME)

        embed = self.ctx.error_embed(
            title=f"{icons.caution} Race Expired",
            description=f"The race was not started in {timespan}",
        )

        await self.ctx.interaction.edit_original_message(embed=embed, view=None)

    def get_race_join_embed(self, started=False):
        embed = self.ctx.embed(title="Typing Test Race", description="** **")

        users = self.get_formatted_users()

        if started:
            extra = "You can no longer join the race"
        else:
            extra = "The race leader can start the race by joining it"

        embed.add_field(
            name=f"Racers ({self.total_racers} / {MAX_RACE_JOIN})",
            value=f"{users}\n\n{extra}",
        )

        embed.add_field(name="** **", value="** **")

        return embed

    async def start(self):
        embed = self.get_race_join_embed()

        race_join_button = RaceJoinButton()
        race_leave_button = RaceLeaveButton()

        self.add_item(race_join_button)
        self.add_item(race_leave_button)

        await self.ctx.respond(embed=embed, view=self)

        self.timeout_race.start()


class Typing(commands.Cog):
    """Typing test related commands"""

    emoji = "\N{KEYBOARD}"
    order = 2

    def __init__(self, bot):
        self.bot = bot

    tt_group = SlashCommandGroup("tt", "Take a typing test")
    race_group = SlashCommandGroup(
        "race",
        f"Take a multiplayer typing test. Up to {MAX_RACE_JOIN} other users can join your race.",
    )

    @cooldown(5, 1)
    @tt_group.command()
    async def dictionary(self, ctx, length: word_amt()):
        """Take a dictionary typing test"""
        quote = await self.handle_dictionary_input(ctx, length)

        await self.do_typing_test(ctx, True, quote, length, ctx.respond)

    @cooldown(5, 1)
    @tt_group.command()
    async def quote(self, ctx, length: quote_amt()):
        """Take a quote typing test"""
        quote = await self.handle_quote_input(length)

        await self.do_typing_test(ctx, False, quote, length, ctx.respond)

    @cooldown(6, 2)
    @race_group.command()
    async def dictionary(self, ctx, length: word_amt()):
        """Take a multiplayer dictionary typing test"""
        quote = await self.handle_dictionary_input(ctx, length)

        await self.show_race_start(ctx, True, quote)

    @cooldown(6, 2)
    @race_group.command()
    async def quote(self, ctx, length: quote_amt()):
        """Take a multiplayer quote typing test"""
        quote = await self.handle_quote_input(length)

        await self.show_race_start(ctx, False, quote)

    @cooldown(6, 2)
    @commands.user_command(name="Typing Challenge")
    async def race_challenge(self, ctx, member: discord.Member):
        # TODO: send a dropdown to choose race
        pass

    @staticmethod
    async def handle_dictionary_input(ctx, length: int):
        if length not in range(TEST_RANGE[0], TEST_RANGE[1] + 1):
            raise commands.BadArgument(
                f"The typing test must be between {TEST_RANGE[0]} and {TEST_RANGE[1]} words"
            )

        user = await ctx.bot.mongo.fetch_user(ctx.author)

        words = load_test_file(word_list.languages[user.language]["levels"][user.level])

        return random.sample(words, length)

    @staticmethod
    async def handle_quote_input(length: str):
        test_range = word_list.quotes["lengths"][length]

        quotes = load_test_file("quotes.json")

        start = random.randint(0, len(quotes) - 1)

        # Selecting consecutive items from list of sentences
        sections = list(
            islice(cycle(quotes), start, start + random.randint(*test_range))
        )

        return [word for p in sections for word in p.split()]

    @staticmethod
    async def show_race_start(ctx, is_dict, quote):
        # Storing is_dict and quote in RaceJoinView because do_race method will be called inside it
        view = RaceJoinView(ctx, is_dict, quote)
        await view.start()

        user = await ctx.bot.mongo.fetch_user(ctx.author)

        # Context tutorial
        if not cmd_run_before(ctx, user):
            await ctx.respond("Start the race by joining it", ephemeral=True)

    @staticmethod
    async def personal_test_input(user, ctx, test_type_int, quote, send):
        # Loading embed

        # fmt: off
        test_type = (
            "Quote"
            if test_type_int == 0

            else "Dictionary"
            if test_type_int == 1

            else "Practice"
            if test_type_int == 2
            
            else None
        )
        # fmt: on

        word_count = len(quote)

        pacer_type_name = get_pacer_type_name(user.pacer_type)

        pacer_name = get_pacer_display(user.pacer_speed)

        if pacer_name != "None":
            pacer_name += f" ({pacer_type_name})"

        title = f"{user.display_name} | {test_type} Test ({word_count} words)"
        desc = f"**Pacer:** {pacer_name}"

        embed = ctx.embed(
            title=title,
            description=desc,
            add_footer=False,
        )

        raw_quote = " ".join(quote)

        word_list, fquote = wrap_text(raw_quote)

        width, height = get_width_height(word_list)

        base_img = get_base(width, height, user.theme, fquote)

        loading_img = get_loading_img(base_img, user.theme[1])

        buffer = BytesIO()
        loading_img.save(buffer, "png")
        buffer.seek(0)

        file = discord.File(buffer, filename="loading.png")

        embed.set_image(url="attachment://loading.png")
        embed.set_thumbnail(url="https://i.imgur.com/CjdaXi6.gif")

        await send(embed=embed, file=file, delete_after=5)

        load_start = time.time()

        # Generating the acutal test image

        # TODO: generate pacer if the user has a pacer

        buffer = BytesIO()
        base_img.save(buffer, "png")
        buffer.seek(0)

        file = discord.File(buffer, filename="test.png")

        embed = ctx.embed(title=title, description=desc, add_footer=False)

        embed.set_image(url="attachment://test.png")

        load_time = time.time() - load_start

        await asyncio.sleep(5 - max(load_time, 0))

        await ctx.respond(embed=embed, file=file)

        start_time = time.time()

        # Waiting for the input from the user

        try:
            message = await ctx.bot.wait_for(
                "message", check=lambda m: m.author == ctx.author, timeout=180
            )
        except asyncio.TimeoutError:
            embed = ctx.error_embed(
                title="Typing Test Expired",
                description="You did not complete the typing test within 5 minutes.\n\nConsider lowering the test length so that you can finish it.",
            )
            return await ctx.respond(embed=embed)

        end_time = round(time.time() - start_time, 2)

        return message, end_time, pacer_name, raw_quote

    @classmethod
    async def do_typing_test(cls, ctx, is_dict, quote, length, send):
        user = await ctx.bot.mongo.fetch_user(ctx.author)

        # Prompting a captcha at intervals to prevent automated accounts
        if (user.test_amt + 1) % CAPTCHA_INTERVAL == 0:
            return await cls.handle_interval_captcha(ctx, user)

        message, end_time, pacer_name, raw_quote = await cls.personal_test_input(
            user, ctx, int(is_dict), quote, send
        )

        # Evaluating the input of the user
        u_input = message.content.split()

        wpm, raw, acc, cc, cw, word_history = get_test_stats(u_input, quote, end_time)

        xp_earned = round(1 + (cc * 2))

        ts = "\N{THIN SPACE}"

        # Sending the results
        # Spacing in title keeps same spacing if word history is short
        embed = ctx.embed(
            title=f"Typing Test Results{ts*110}\n\n`Statistics`",
        )

        embed.set_author(
            name=ctx.author,
            icon_url=ctx.author.display_avatar.url,
        )

        embed.set_thumbnail(url="https://i.imgur.com/l9sLfQx.png")

        # Statistics

        space = " "

        embed.add_field(name=":person_walking: Wpm", value=wpm)

        embed.add_field(name=":person_running: Raw Wpm", value=raw)

        embed.add_field(name=":dart: Accuracy", value=f"{acc}%")

        embed.add_field(name=":clock1: Time", value=f"{end_time}s")

        embed.add_field(name=f"{icons.xp} Experience", value=xp_earned)

        embed.add_field(name=f":x: Mistakes", value=len(u_input) - cw)

        embed.add_field(
            name="** **",
            value=f"**Word History**\n> {word_history}\n\n```ini\n{space*13}[ Test Settings ]```\n** **",
            inline=False,
        )

        # Settings
        embed.add_field(
            name=":earth_americas: Language", value=user.language.capitalize()
        )

        embed.add_field(name=":timer: Pacer", value=pacer_name)

        embed.add_field(
            name=":1234: Words", value=f"{len(quote)} ({len(raw_quote)} chars)"
        )

        view = TestResultView(ctx, user, is_dict, quote, length)

        view.message = await message.reply(embed=embed, view=view, mention_author=False)

        # Checking if there is a new high score

        user.xp += xp_earned
        user.words += cw
        user.test_amt += 1

        result = get_test_zone(cw)

        if result is None:
            await ctx.respond(
                "Warning: Tests below 10 correct words are not saved", ephemeral=True
            )
        else:
            zone, zone_range = result

            score = ctx.bot.mongo.Score(
                wpm=wpm,
                raw=raw,
                acc=acc,
                cw=cw,
                tw=len(quote),
                u_input=u_input,
                quote=quote,
                xp=xp_earned,
                timestamp=datetime.utcnow(),
            )

            user.scores.append(score)

            if wpm > user.highspeed[zone].wpm:
                user.highspeed[zone] = score

                embed = ctx.embed(
                    title=":trophy: New High Score",
                    description=f"You got a new high score of **{wpm}** on the {zone} test {zone_range}",
                )

                await ctx.respond(embed=embed)

        await ctx.bot.mongo.replace_user_data(user)

    @staticmethod
    async def handle_interval_captcha(ctx, user):
        # Getting the quote for the captcha
        words = load_test_file(word_list.languages["english"]["levels"]["easy"])
        captcha_word = random.choice(words)

        # Generating the captcha image
        image = ImageCaptcha(width=200)
        buffer = image.generate(captcha_word)
        buffer.seek(0)

        embed = ctx.embed(
            title=":robot: Captcha", description="Type the word below", add_footer=False
        )

        file = discord.File(fp=buffer, filename="captcha.png")

        embed.set_image(url="attachment://captcha.png")

        await ctx.respond(embed=embed, file=file)

        # Waiting for user input
        try:
            message = await ctx.bot.wait_for(
                "message", check=lambda m: m.author == ctx.author, timeout=120
            )
        except asyncio.TimeoutError:
            embed = ctx.error_embed(
                title="Captcha Expired",
                description="You did not complete the captcha within 2 minutes",
            )
            return await ctx.respond(embed=embed)

        # Evaluating the success of the captcha
        if message.content.lower() == captcha_word:
            embed = ctx.embed(
                title=f"{icons.success} Captcha Completed", add_footer=False
            )
            return await ctx.respond(embed=embed)

        embed = ctx.error_embed(title=f"{icons.caution} Captcha Failed")

        await ctx.respond(embed=embed)

    @staticmethod
    async def do_race(ctx, racers, is_dict, quote):
        """
        racers: dict
        is_dict: bool (if it's a dictionary race)
        quote: list
        """


def setup(bot):
    bot.add_cog(Typing(bot))
