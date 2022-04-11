import asyncio
import json
import math
import random
import textwrap
import time
from datetime import datetime
from io import BytesIO
from itertools import groupby

import discord
from captcha.image import ImageCaptcha
from discord.commands import SlashCommandGroup
from discord.ext import commands, tasks
from discord.utils import escape_markdown
from humanfriendly import format_timespan

import icons
import word_list
from constants import (
    CAPTCHA_ACC_PERC,
    CAPTCHA_INTERVAL,
    CAPTCHA_WPM_DEC,
    DEFAULT_WRAP,
    MAX_CAPTCHA_ATTEMPTS,
    MAX_RACE_JOIN,
    RACE_JOIN_EXPIRE_TIME,
    SUPPORT_SERVER_INVITE,
    TEST_EXPIRE_TIME,
    TEST_RANGE,
    TEST_ZONES,
)
from helpers.checks import cooldown
from helpers.converters import quote_amt, word_amt
from helpers.image import (
    get_base,
    get_highscore_captcha_img,
    get_loading_img,
    get_width_height,
    wrap_text,
)
from helpers.ui import BaseView, create_link_view, get_log_embed
from helpers.user import get_pacer_display, get_pacer_type_name
from helpers.utils import cmd_run_before, get_test_stats


def load_test_file(name):
    with open(f"./word_list/{name}", "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    return data["words"], data.get("wrap", DEFAULT_WRAP)


def author_is_user(ctx):
    return lambda m: m.author.id == ctx.author.id


def get_test_zone_name(cw):
    for n, r in TEST_ZONES.items():
        if cw in r:
            return n, f"({r[0]}-{r[-1]}) words"

    return None


def get_xp_earned(cc):
    return round(1 + (cc * 2))


def get_test_type(test_type_int: int, length: int):
    zone = next(
        (f"{t.capitalize()} " for t, v in TEST_ZONES.items() if length in v), ""
    )

    # fmt: off
    return zone + (
        "Quote"
        if test_type_int == 0

        else "Dictionary"
        if test_type_int == 1

        else "Practice"
        if test_type_int == 2
        
        else None
        )
    # fmt: on


HIGH_SCORE_CAPTCHA_TIMEOUT = 60


def invoke_completion(ctx):
    ctx.no_completion = False
    ctx.bot.dispatch("application_command_completion", ctx)


class RetryView(BaseView):
    def __init__(self, ctx, captcha_callback):
        super().__init__(ctx, timeout=HIGH_SCORE_CAPTCHA_TIMEOUT)

        self.captcha_callback = captcha_callback

    async def on_timeout(self):
        await super().on_timeout()

        invoke_completion(self.ctx)

    @discord.ui.button(label="Retry", style=discord.ButtonStyle.success)
    async def retry_captcha(self, button, interaction):
        await self.captcha_callback(self, button, interaction)


class HighScoreCaptchaView(BaseView):
    def __init__(self, ctx, user, original_wpm):
        super().__init__(ctx, timeout=HIGH_SCORE_CAPTCHA_TIMEOUT)

        self.user = user
        self.original_wpm = original_wpm
        self.attempts = 0

    async def on_timeout(self):
        await super().on_timeout()

        invoke_completion(self.ctx)

    @property
    def target(self):
        return int(self.original_wpm * (1 - CAPTCHA_WPM_DEC))

    @discord.ui.button(label="Start Captcha", style=discord.ButtonStyle.success)
    async def start_captcha(self, button, interaction):
        await self.handle_captcha(self, button, interaction)

    async def flag_captcha_fail(self, wpm):
        embed = get_log_embed(
            self.ctx,
            title="High Score Captcha Fail",
            additional=(
                f"**Orignal Wpm:** {self.original_wpm}\n"
                f"**Attempts:** {self.attempts}\n"
                f"**Wpm:** {wpm}"
            ),
        )

        await self.ctx.bot.test_wh.send(embed=embed)

        if self.original_wpm:
            await self.ctx.bot.impt_wh.send(embed=embed)

    async def handle_captcha(self, view, button, interaction):
        button.disabled = True

        await self.message.edit(view=view)

        # Generating the quote for the test
        quote, wrap_width = await Typing.handle_dictionary_input(self.ctx, 35)

        raw_quote = " ".join(quote)

        word_list, fquote = wrap_text(raw_quote, wrap_width)

        width, height = get_width_height(word_list, wrap_width)

        base_img = get_base(width, height, self.user.theme, fquote)

        captcha_img = get_highscore_captcha_img(base_img, self.user.theme[1])

        captcha_loading_img = get_loading_img(captcha_img, self.user.theme[1])

        buffer = BytesIO()
        captcha_loading_img.save(buffer, "png")
        buffer.seek(0)

        embed = self.ctx.embed(title="High Score Captcha")

        file = discord.File(buffer, filename="captcha.png")

        embed.set_image(url="attachment://captcha.png")
        embed.set_thumbnail(url="https://i.imgur.com/ZRfx4yz.gif")

        await interaction.response.send_message(embed=embed, file=file, delete_after=5)

        load_start = time.time()

        buffer = BytesIO()
        captcha_img.save(buffer, "png")
        buffer.seek(0)

        file = discord.File(buffer, filename="test.png")

        embed = self.ctx.embed(title="High Score Captcha")

        embed.set_image(url="attachment://test.png")

        load_time = time.time() - load_start

        await asyncio.sleep(5 - max(load_time, 0))

        await self.ctx.respond(embed=embed, file=file)

        start_time = time.time()

        tc = len(raw_quote)

        # Calculating the expire time based on the target wpm
        expire_time = (12 * tc) / self.target + 2

        finished_test = True

        try:
            message = await self.ctx.bot.wait_for(
                "message",
                check=author_is_user(self.ctx),
                timeout=expire_time,
            )
        except asyncio.TimeoutError:
            finished_test = False

        raw = None

        if finished_test:
            end_time = time.time() - start_time

            u_input = message.content.split()

            _, raw, _, cc, _, word_history = get_test_stats(u_input, quote, end_time)

            ratio = cc / len(" ".join(quote))

            acc = round(ratio * 100, 2)
            raw = round(raw * ratio, 2)

            # Checking if the test was passed
            if math.ceil(raw) >= self.target and math.ceil(acc) >= CAPTCHA_ACC_PERC:
                embed = self.ctx.embed(
                    title="Passed", description="You passed the high score captcha!"
                )

                embed.add_field(
                    name=":x: Attempts",
                    value=f"{self.attempts} / {MAX_CAPTCHA_ATTEMPTS}",
                )

                embed = self.add_results(embed, raw, acc, word_history)

                await self.ctx.respond(embed=embed)

                await self.ctx.bot.mongo.replace_user_data(self.user)

                return invoke_completion(self.ctx)

        self.attempts += 1

        attempts_left = MAX_CAPTCHA_ATTEMPTS - self.attempts

        embed = self.ctx.error_embed(title="Failed")

        if finished_test:
            embed = self.add_results(embed, raw, acc, word_history)

        if attempts_left == 0:
            embed.description = "You have no more attempts left"

            await self.ctx.respond(embed=embed)

            invoke_completion(self.ctx)

            return await self.flag_captcha_fail(raw)

        plural = "s" if attempts_left > 1 else ""

        embed.description = f"You have **{attempts_left}** attempt{plural} left."

        view = RetryView(self.ctx, self.handle_captcha)

        view.message = await self.ctx.respond(embed=embed, view=view)

        await self.flag_captcha_fail(raw)

    def add_results(self, embed, raw, acc, word_history):
        embed.add_field(name=":person_running: Raw Wpm", value=f"{raw} / {self.target}")

        embed.add_field(name=":dart: Accuracy", value=f"{acc}% / {CAPTCHA_ACC_PERC}%")

        embed.add_field(
            name="Word History", value=word_history or "** **", inline=False
        )

        return embed

    async def start(self):
        embed = self.ctx.embed(
            title="High Score Captcha",
            description=(
                f"You got a new high score of **{self.original_wpm}**!\n\n"
                "Please complete a short typing test captcha so we can make\n"
                "sure you aren't being dishonest.\n\n"
                "You won't have to take this test again until you beat your\n"
                f"new high score by **{int(CAPTCHA_WPM_DEC*100)}%**.\n\n"
                f"Type at least **{self.target}** raw wpm with **{CAPTCHA_ACC_PERC}%+** accuracy to pass."
            ),
        )

        self.message = await self.ctx.respond(embed=embed, view=self)


class TestResultView(BaseView):
    def __init__(self, ctx, user, is_dict, quote, wrap_width, length):
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
        self.wrap_width = wrap_width

        self.user = user

    @discord.ui.button(label="Next Test", style=discord.ButtonStyle.success)
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
        test_info = (self.quote, self.wrap_width)

        result = await Typing.personal_test_input(
            self.user, self.ctx, 2, test_info, interaction.response.send_message
        )

        if result is None:
            return

        message, end_time, pacer_name, raw_quote = result

        u_input = message.content.split()

        wpm, raw, acc, _, cw, word_history = get_test_stats(
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

        await self.ctx.respond("Warning: Practice tests are not saved")


class RaceMember:
    def __init__(self, user, data):
        """
        user: user object
        """
        self.user = user

        # User's database document
        self.data = data

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
    def __init__(self, ctx, is_dict, quote, wrap_width):
        super().__init__(ctx, timeout=None, personal=False)

        self.is_dict = is_dict
        self.quote = quote
        self.wrap_width = wrap_width
        self.racers = {}  # id: user object (for preserve uniqueness)

        self.race_msg = None
        self.start_time = None

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

    def get_race_embed(self):
        test_type = get_test_type(int(self.is_dict), len(self.quote))

        embed = self.ctx.embed(
            title=f"{test_type} Race",
            description="\n".join(
                f"{r.data.display_name}"
                + ("" if r.result is None else " :checkered_flag:")
                for r in self.racers.values()
            ),
            add_footer=False,
        )

        return embed

    async def handle_racer_finish(self, m):
        end_time = time.time() - self.start_time

        r = self.racers[m.author.id]

        u_input = m.content.split()

        wpm, raw, _, cc, cw, _ = get_test_stats(u_input, self.quote, end_time)

        ratio = cc / len(" ".join(self.quote))

        acc = round(ratio * 100, 2)
        wpm = round(wpm * ratio, 2)
        raw = round(raw * ratio, 2)

        xp_earned = get_xp_earned(cc)

        r.result = self.ctx.bot.mongo.Score(
            wpm=wpm,
            raw=raw,
            acc=acc,
            cw=cw,
            tw=len(self.quote),
            xp=xp_earned,
            timestamp=datetime.utcnow(),
        )
        embed = self.get_race_embed()
        embed.set_image(url="attachment://test.png")

        await self.race_msg.edit(embed=embed)

    async def do_race(self, interaction):

        author_theme = self.racers[self.ctx.author.id].data.theme

        raw_quote = " ".join(self.quote)

        word_list, fquote = wrap_text(raw_quote, self.wrap_width)

        width, height = get_width_height(word_list, self.wrap_width)

        base_img = get_base(width, height, author_theme, fquote)

        loading_img = get_loading_img(base_img, author_theme[1])

        buffer = BytesIO()
        loading_img.save(buffer, "png")
        buffer.seek(0)

        # Loading image
        embed = self.get_race_embed()

        file = discord.File(buffer, filename="loading.png")

        embed.set_image(url="attachment://loading.png")
        embed.set_thumbnail(url="https://i.imgur.com/ZRfx4yz.gif")

        await interaction.response.send_message(embed=embed, file=file, delete_after=5)

        load_start = time.time()

        buffer = BytesIO()
        base_img.save(buffer, "png")
        buffer.seek(0)

        file = discord.File(buffer, filename="test.png")

        embed = self.get_race_embed()

        embed.set_image(url="attachment://test.png")

        load_time = time.time() - load_start

        await asyncio.sleep(5 - max(load_time, 0))

        self.race_msg = await self.ctx.respond(embed=embed, file=file)

        self.start_time = time.time()

        try:
            await asyncio.wait_for(self.wait_for_inputs(), timeout=TEST_EXPIRE_TIME)
        except asyncio.TimeoutError:
            embed = self.ctx.error_embed(
                title="Race Ended",
                description=f"The race automatically ends after {format_timespan(TEST_EXPIRE_TIME)}",
            )

            await self.ctx.respond(embed=embed)

        await self.send_race_results()

    async def wait_for_inputs(self):
        for _ in range(len(self.racers)):
            # Waiting for the input from all the users
            message = await self.ctx.bot.wait_for(
                "message",
                check=lambda m: (r := self.racers.get(m.author.id, None)) is not None
                and r.result is None,
            )

            try:
                await message.delete()
            except discord.errors.Forbidden:
                pass

            await self.handle_racer_finish(message)

    async def send_race_results(self):
        embed = self.ctx.embed(
            title="Race Results",
            description="Results are adjusted to the portion of test completed",
        )

        key_wpm = lambda r: r.result.wpm if r.result else 0

        sorted_results = sorted(self.racers.values(), key=key_wpm, reverse=True)

        grouped_results = groupby(sorted_results, key=key_wpm)

        for i, (_, g) in enumerate(grouped_results):
            place_display = f"`{i+1}.`" if i != 0 else ":first_place:"

            long_space = "\N{IDEOGRAPHIC SPACE}"

            for r in g:
                user = r.data
                score = r.result

                if r.result is None:
                    value = f"** **{long_space}__Not Finished__"
                else:
                    value = (
                        f"** **{long_space}:person_walking: Wpm: **{score.wpm}**\n"
                        f"{long_space} :person_running: Raw Wpm: **{score.raw}**\n"
                        f"{long_space} :dart: Accuracy: **{score.acc}%**"
                    )
                    user.add_score(score)
                    user.add_words(score.cw)
                    user.add_xp(score.xp)

                embed.add_field(
                    name=f"{place_display} {r.data.display_name}",
                    value=value,
                    inline=False,
                )

        embed.set_thumbnail(url="https://i.imgur.com/l9sLfQx.png")

        view = create_link_view(
            {
                "Invite Bot": self.ctx.bot.create_invite_link(),
                "Community Server": SUPPORT_SERVER_INVITE,
            }
        )

        await self.ctx.respond(embed=embed, view=view)

        # Updating the users in the database
        for r in self.racers.values():
            if r.result is not None:
                await self.ctx.bot.mongo.replace_user_data(r.data)

    async def add_racer(self, interaction):
        if len(self.racers) == MAX_RACE_JOIN:
            return await interaction.response.send_message(
                f"The race has reached its maximum capacity of {MAX_RACE_JOIN} racers"
            )

        user = interaction.user

        user_data = await self.ctx.bot.mongo.fetch_user(user)

        # TODO: create an account for them
        if user_data is None:
            return

        if user_data.banned:
            return await interaction.response.send_message(
                "You are banned", ephemeral=True
            )

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

        else:
            bucket = self.race_join_cooldown.get_bucket(interaction.message)

            retry_after = bucket.update_rate_limit()

            if retry_after:
                timespan = format_timespan(retry_after)

                return await interaction.response.send_message(
                    f"Sorry you are being rate limited, try again in {timespan}",
                    ephemeral=True,
                )

        self.racers[user.id] = RaceMember(user, user_data)

        embed = self.get_race_join_embed(is_author)

        await msg.edit(embed=embed, view=self)

        if is_author:
            self.stop()
            self.timeout_race.stop()
            await self.do_race(interaction)

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
    @tasks.loop(seconds=RACE_JOIN_EXPIRE_TIME, count=2)
    async def timeout_race(self):
        if self.timeout_race.current_loop == 1:
            await self.send_expire_race_message()
            self.stop()

    async def send_expire_race_message(self):
        timespan = format_timespan(RACE_JOIN_EXPIRE_TIME)

        embed = self.ctx.error_embed(
            title=f"{icons.caution} Race Expired",
            description=f"The race was not started within {timespan}",
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

    @commands.max_concurrency(1, per=commands.BucketType.user)
    @cooldown(5, 1)
    @tt_group.command()
    async def dictionary(self, ctx, length: word_amt()):
        """Take a dictionary typing test"""
        quote_info = await self.handle_dictionary_input(ctx, length)

        await self.do_typing_test(ctx, True, quote_info, length, ctx.respond)

    @commands.max_concurrency(1, per=commands.BucketType.user)
    @cooldown(5, 1)
    @tt_group.command()
    async def quote(self, ctx, length: quote_amt()):
        """Take a quote typing test"""
        quote_info = await self.handle_quote_input(length)

        await self.do_typing_test(ctx, False, quote_info, length, ctx.respond)

    @commands.max_concurrency(1, per=commands.BucketType.user)
    @cooldown(6, 2)
    @race_group.command()
    async def dictionary(self, ctx, length: word_amt()):
        """Take a multiplayer dictionary typing test"""
        quote_info = await self.handle_dictionary_input(ctx, length)

        await self.show_race_start(ctx, True, quote_info)

    @commands.max_concurrency(1, per=commands.BucketType.user)
    @cooldown(6, 2)
    @race_group.command()
    async def quote(self, ctx, length: quote_amt()):
        """Take a multiplayer quote typing test"""
        quote_info = await self.handle_quote_input(length)

        await self.show_race_start(ctx, False, quote_info)

    @staticmethod
    async def handle_dictionary_input(ctx, length: int):
        if length not in range(TEST_RANGE[0], TEST_RANGE[1] + 1):
            raise commands.BadArgument(
                f"The typing test must be between {TEST_RANGE[0]} and {TEST_RANGE[1]} words"
            )

        user = await ctx.bot.mongo.fetch_user(ctx.author)

        words, wrap = load_test_file(word_list.languages[user.language][user.level])

        return random.sample(words, length), wrap

    @staticmethod
    async def handle_quote_input(length: str):
        quotes, wrap = load_test_file("quotes.json")

        # Getting the maximum amount of words for that test zone
        max_words = TEST_ZONES[length][-1]

        # Selecting consecutive items from list of sentences within max word amount
        start = random.randint(0, len(quotes))

        words = []

        last = None

        while last is None or len(last) + len(words) <= max_words:
            if last is not None:
                words += last

            last = quotes[(len(words) + start) % len(quotes)].split()

        return words, wrap

    @staticmethod
    async def show_race_start(ctx, is_dict, quote_info):
        # Storing is_dict and quote in RaceJoinView because do_race method will be called inside it
        view = RaceJoinView(ctx, is_dict, *quote_info)
        await view.start()

        user = await ctx.bot.mongo.fetch_user(ctx.author)

        # Context tutorial
        if not cmd_run_before(ctx, user):
            await ctx.respond("Start the race by joining it", ephemeral=True)

    @staticmethod
    async def personal_test_input(user, ctx, test_type_int, quote_info, send):
        quote, wrap_width = quote_info

        # Loading embed

        word_count = len(quote)

        test_type = get_test_type(test_type_int, word_count)

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

        word_list, fquote = wrap_text(raw_quote, wrap_width)

        width, height = get_width_height(word_list, wrap_width)

        base_img = get_base(width, height, user.theme, fquote)

        loading_img = get_loading_img(base_img, user.theme[1])

        buffer = BytesIO()
        loading_img.save(buffer, "png")
        buffer.seek(0)

        file = discord.File(buffer, filename="loading.png")

        embed.set_image(url="attachment://loading.png")
        embed.set_thumbnail(url="https://i.imgur.com/ZRfx4yz.gif")

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

        if not cmd_run_before(ctx, user):
            await ctx.respond("Type the text above!", ephemeral=True)

        # Waiting for the input from the user

        try:
            message = await ctx.bot.wait_for(
                "message",
                check=author_is_user(ctx),
                timeout=TEST_EXPIRE_TIME,
            )
        except asyncio.TimeoutError:
            embed = ctx.error_embed(
                title="Typing Test Expired",
                description=(
                    f"You did not complete the typing test within {format_timespan(TEST_EXPIRE_TIME)}.\n\n"
                    "Consider lowering the test length so that you can finish it."
                ),
            )
            await ctx.respond(embed=embed)
            return None

        end_time = round(time.time() - start_time, 2)

        return message, end_time, pacer_name, raw_quote

    @classmethod
    async def do_typing_test(cls, ctx, is_dict, quote_info, length, send):
        quote, _ = quote_info

        user = await ctx.bot.mongo.fetch_user(ctx.author)

        # Prompting a captcha at intervals to prevent automated accounts
        if (user.test_amt + 1) % CAPTCHA_INTERVAL == 0:
            return await cls.handle_interval_captcha(ctx, user)

        result = await cls.personal_test_input(
            user, ctx, int(is_dict), quote_info, send
        )

        if result is None:
            return

        message, end_time, pacer_name, raw_quote = result

        # Evaluating the input of the user
        u_input = message.content.split()

        wpm, raw, acc, cc, cw, word_history = get_test_stats(u_input, quote, end_time)

        xp_earned = get_xp_earned(cc)

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

        view = TestResultView(ctx, user, is_dict, *quote_info, length)

        view.message = await message.reply(embed=embed, view=view, mention_author=False)

        # Checking if there is a new high score

        user.test_amt += 1

        user.add_xp(xp_earned)
        user.add_words(cw)

        result = get_test_zone_name(cw)

        warning = ""

        if raw > 350:
            warning = "Please try not to spam the test."

        elif acc < 75:
            warning = "Tests below 75% accuracy are not saved."

        elif result is None:
            warning = "Tests below 10 correct words are not saved."

        if warning:
            await ctx.respond(f"Warning: {warning}", ephemeral=True)

        else:
            zone, zone_range = result

            score = ctx.bot.mongo.Score(
                wpm=wpm,
                raw=raw,
                acc=acc,
                cw=cw,
                tw=len(quote),
                xp=xp_earned,
                timestamp=datetime.utcnow(),
            )

            check = user.highest_speed * (1 + CAPTCHA_WPM_DEC)

            user.add_score(score)

            if wpm > user.highspeed[zone].wpm:
                user.highspeed[zone] = score

                embed = ctx.embed(
                    title=":trophy: New High Score",
                    description=f"You got a new high score of **{wpm}** on the {zone} test {zone_range}",
                )

                await ctx.respond(embed=embed)

                # Test high score anti cheat system

                if check <= wpm >= 100:
                    # Preventing on_application_command_completion from being invoked
                    ctx.no_completion = True

                    view = HighScoreCaptchaView(ctx, user, wpm)

                    return await view.start()

        await ctx.bot.mongo.replace_user_data(user)

    @staticmethod
    async def handle_interval_captcha(ctx, user):
        # Getting the quote for the captcha
        words, _ = load_test_file(word_list.languages["english"]["easy"])
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
                "message", check=author_is_user(ctx), timeout=120
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
            await ctx.respond(embed=embed)

            user.test_amt += 1

            return await ctx.bot.mongo.replace_user_data(user)

        embed = ctx.error_embed(title=f"{icons.caution} Captcha Failed")

        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(Typing(bot))
