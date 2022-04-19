import asyncio
import json
import math
import random
import textwrap
import time
from datetime import datetime, timezone
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
    SUSPICIOUS_THRESHOLD,
    TEST_EXPIRE_TIME,
    TEST_RANGE,
    TEST_ZONES,
)
from helpers.checks import cooldown
from helpers.converters import quote_amt, word_amt
from helpers.image import (
    get_base_img,
    get_highscore_captcha_img,
    get_loading_img,
    save_img_as_discord_png,
)
from helpers.ui import BaseView, create_link_view, get_log_embed
from helpers.user import get_pacer_display, get_pacer_type_name
from helpers.utils import cmd_run_before, get_test_stats

HIGH_SCORE_CAPTCHA_TIMEOUT = 60


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


def get_word_display(quote, raw_quote):
    return f"{len(quote)} ({len(raw_quote)} chars)"


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


def invoke_completion(ctx):
    ctx.no_completion = False
    ctx.bot.dispatch("application_command_completion", ctx)


def get_log_additional(wpm, raw, acc, word_display, xp_earned):
    return (
        f"**Wpm:** {wpm}\n"
        f"**Raw:** {raw}\n"
        f"**Accuracy:** {acc}\n"
        f"**Word Amount:** {word_display}\n"
        f"**XP:** {xp_earned}"
    )


def get_test_warning(raw, acc, result):
    if raw > 350:
        return "Please try not to spam the test."

    if acc < 75:
        return "Tests below 75% accuracy are not saved."

    if result is None:
        return "Tests below 10 correct words are not saved."

    return None


def add_test_stats_to_embed(
    embed,
    wpm,
    raw,
    acc,
    end_time,
    tw,
    cw,
    word_history,
    language,
    pacer_name,
    word_display,
    xp_earned=None,
):
    space = " "

    embed.add_field(name=":person_walking: Wpm", value=wpm)
    embed.add_field(name=":person_running: Raw Wpm", value=raw)
    embed.add_field(name=":dart: Accuracy", value=f"{acc}%")

    embed.add_field(name=":clock1: Time", value=f"{end_time}s")

    if xp_earned is not None:
        embed.add_field(name=f"{icons.xp} Experience", value=xp_earned)

    embed.add_field(name=f":x: Mistakes", value=tw - cw)

    embed.add_field(
        name="** **",
        value=f"**Word History**\n> {word_history}\n\n```ini\n{space*13}[ Test Settings ]```\n** **",
        inline=False,
    )

    # Settings
    embed.add_field(name=":earth_americas: Language", value=language.capitalize())
    embed.add_field(name=":timer: Pacer", value=pacer_name)
    embed.add_field(name=":1234: Words", value=word_display)

    embed.set_thumbnail(url="https://i.imgur.com/l9sLfQx.png")

    return embed


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

    async def log_captcha_completion(self, raw, acc, failed: bool):
        completion_type = "Fail" if failed else "Pass"

        embed = get_log_embed(
            self.ctx,
            title=f"High Score Captcha {completion_type}",
            additional=(
                f"**Orignal Wpm:** {self.original_wpm}\n"
                f"**Raw:** {raw} / {self.target}\n"
                f"**Acc:** {acc} / {CAPTCHA_ACC_PERC}\n"
                f"**Attempts:** {self.attempts} / {MAX_CAPTCHA_ATTEMPTS}"
            ),
            error=failed,
        )

        await self.ctx.bot.test_wh.send(embed=embed)

        if failed and self.original_wpm >= SUSPICIOUS_THRESHOLD:
            await self.ctx.bot.impt_wh.send(embed=embed)

    async def handle_captcha(self, view, button, interaction):
        self.ctx.bot.active_start(self.ctx.author.id)

        button.disabled = True

        await self.message.edit(view=view)

        # Generating the quote for the test
        quote, wrap_width = await Typing.handle_dictionary_input(self.ctx, 35)

        raw_quote = " ".join(quote)

        base_img = get_base_img(raw_quote, wrap_width, self.user.theme)

        captcha_img = get_highscore_captcha_img(base_img, self.user.theme[1])

        captcha_loading_img = get_loading_img(captcha_img, self.user.theme[1])

        file = save_img_as_discord_png(captcha_loading_img, "captcha")

        # Generating the loading embed

        embed = self.ctx.embed(title="High Score Captcha")

        embed.set_image(url="attachment://captcha.png")
        embed.set_thumbnail(url="https://i.imgur.com/ZRfx4yz.gif")

        await interaction.response.send_message(embed=embed, file=file, delete_after=5)

        load_start = time.time()

        file = save_img_as_discord_png(captcha_img, "test")

        # Generating the test embed

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

        self.ctx.bot.active_end(self.ctx.author.id)

        raw = None

        if finished_test:
            end_time = round(message.created_at.timestamp() - start_time, 2)

            u_input = message.content.split()

            _, raw, _, cc, _, word_history = get_test_stats(u_input, quote, end_time)

            ratio = cc / len(" ".join(quote))

            acc = round(ratio * 100, 2)
            raw = round(raw * ratio, 2)

            # Checking if the test was passed
            if math.ceil(raw) >= self.target and acc >= CAPTCHA_ACC_PERC:
                embed = self.ctx.embed(
                    title="Passed", description="You passed the high score captcha!"
                )

                embed.add_field(
                    name=":x: Attempts",
                    value=f"{self.attempts} / {MAX_CAPTCHA_ATTEMPTS}",
                )

                embed = self.add_results(embed, raw, acc, word_history)

                await self.ctx.respond(embed=embed)

                await self.ctx.bot.mongo.replace_user_data(self.user, self.ctx.author)

                invoke_completion(self.ctx)

                # Logging the pass of the high score captcha
                return await self.log_captcha_completion(raw, acc, False)

        self.attempts += 1

        attempts_left = MAX_CAPTCHA_ATTEMPTS - self.attempts

        embed = self.ctx.error_embed(title="Failed")

        if finished_test:
            embed = self.add_results(embed, raw, acc, word_history)

        if attempts_left == 0:
            embed.description = "You have no more attempts left"

            await self.ctx.respond(embed=embed)

            invoke_completion(self.ctx)

            return await self.log_captcha_completion(raw, acc, True)

        plural = "s" if attempts_left > 1 else ""

        embed.description = f"You have **{attempts_left}** attempt{plural} left."

        view = RetryView(self.ctx, self.handle_captcha)

        view.message = await self.ctx.respond(embed=embed, view=view)

        await self.log_captcha_completion(raw, acc, True)

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

    async def disable_btn(self, button):
        button.disabled = True

        await self.message.edit(view=self)

    @discord.ui.button(label="Next Test", style=discord.ButtonStyle.success)
    async def next_test(self, button, interaction):
        await self.disable_btn(button)

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
        invoke_completion(self.ctx)

    @discord.ui.button(label="Practice Test", style=discord.ButtonStyle.primary)
    async def practice_test(self, button, interaction):
        self.ctx.bot.active_start(self.ctx.author.id)

        await self.disable_btn(button)

        test_info = (self.quote, self.wrap_width)

        result = await Typing.personal_test_input(
            self.user, self.ctx, 2, test_info, interaction.response.send_message
        )

        if result is None:
            self.ctx.bot.active_end(self.ctx.author.id)
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

        word_display = get_word_display(self.quote, raw_quote)

        embed = add_test_stats_to_embed(
            embed,
            wpm,
            raw,
            acc,
            end_time,
            len(u_input),
            cw,
            word_history,
            self.user.language,
            pacer_name,
            word_display,
        )

        await message.reply(embed=embed, mention_author=False)

        await self.ctx.respond("Warning: Practice tests are not saved")

        self.ctx.bot.active_end(self.ctx.author.id)


class RaceMember:
    def __init__(self, user, data, send):
        # user object
        self.user = user

        # User's database document
        self.data = data

        # Function for sending ephemeral messages to user
        self.send = send

        # The test score (mongo.Score)
        self.result = None

        self.save_score = True

        self.zone = None


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
    def __init__(self, ctx, user, is_dict, quote, wrap_width):
        super().__init__(ctx, timeout=None, personal=False)

        self.user = user

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

        self.add_author_to_race()

    def add_author_to_race(self):
        author = self.ctx.author

        race_member = RaceMember(author, self.user, self.ctx.respond)
        self.racers[author.id] = race_member

    def end_all_racers(self):
        for r in self.racers:
            self.ctx.bot.active_end(r)

    async def remove_racer(self, interaction):
        user = interaction.user

        self.ctx.bot.active_end(user.id)

        # If the author leaves, the race is ended
        is_author = user.id == self.ctx.author.id

        msg = (
            self.ctx.interaction.message
            or await self.ctx.interaction.original_message()
        )

        if is_author:
            self.end_all_racers()

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
                + (
                    ""
                    if r.result is None
                    else f" :checkered_flag: **{r.result.wpm} wpm**"
                )
                for r in self.racers.values()
            ),
            add_footer=False,
        )

        return embed

    async def handle_racer_finish(self, m):
        self.ctx.bot.active_end(m.author.id)

        end_time = round(m.created_at.timestamp() - self.start_time, 2)

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
            is_race=True,
        )

        embed = self.get_race_embed()
        embed.set_image(url="attachment://test.png")

        await self.race_msg.edit(embed=embed)

    async def do_race(self, interaction):

        author_theme = self.racers[self.ctx.author.id].data.theme

        raw_quote = " ".join(self.quote)

        base_img = get_base_img(raw_quote, self.wrap_width, author_theme)

        loading_img = get_loading_img(base_img, author_theme[1])

        file = save_img_as_discord_png(loading_img, "loading")

        # Loading image
        embed = self.get_race_embed()

        embed.set_image(url="attachment://loading.png")
        embed.set_thumbnail(url="https://i.imgur.com/ZRfx4yz.gif")

        await interaction.response.send_message(embed=embed, file=file, delete_after=5)

        load_start = time.time()

        file = save_img_as_discord_png(base_img, "test")

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
                score = r.result

                if r.result is None:
                    value = f"** **{long_space}__Not Finished__"
                else:
                    value = (
                        f"** **{long_space}:person_walking: Wpm: **{score.wpm}**\n"
                        f"{long_space} :person_running: Raw Wpm: **{score.raw}**\n"
                        f"{long_space} :dart: Accuracy: **{score.acc}%**"
                    )

                    test_zone = get_test_zone_name(score.cw)

                    warning = get_test_warning(score.raw, score.acc, test_zone)

                    r.zone = test_zone

                    if warning is not None:
                        r.save_score = False
                        value += f"\n{long_space} Warning: {warning}"

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

        # For logging the race
        embeds = []

        raw_quote = " ".join(self.quote)

        word_display = get_word_display(self.quote, raw_quote)

        race_size_display = f"\n**Race Size:** {len(self.racers)}"

        # Updating the users in the database
        for r in self.racers.values():
            score = r.result

            if score is not None:
                if r.save_score:
                    # Refetching user to account for state changes
                    user = await self.ctx.bot.mongo.fetch_user(r.user)

                    user.add_score(score)
                    user.add_words(score.cw)
                    user.add_xp(score.xp)

                    await self.ctx.bot.mongo.replace_user_data(user, r.user)

                additional = get_log_additional(
                    score.wpm, score.raw, score.acc, word_display, score.xp
                )

                is_hs = False

                if r.zone is not None:
                    zone, zone_range = r.zone

                    if score.wpm > r.data.highspeed[zone].wpm:
                        # TODO: send a message showing high score and high score captcha if applicable
                        is_hs = True

                await Typing.log_typing_test(
                    self.ctx, "Race", score.wpm, additional, is_hs
                )

                embed = get_log_embed(
                    self.ctx,
                    title="Race",
                    additional=additional + race_size_display,
                    author=r.user,
                )

            embeds.append(embed)

        for i in range(0, len(embeds), 10):
            show_embeds = embeds[i : i + 10]

            await self.ctx.bot.test_wh.send(embeds=show_embeds)

    async def add_racer(self, interaction):
        if len(self.racers) == MAX_RACE_JOIN - 1:
            return await interaction.response.send_message(
                f"The race has reached its maximum capacity of {MAX_RACE_JOIN} racers"
            )

        user = interaction.user
        is_author = user.id == self.ctx.author.id

        user_data = await self.ctx.bot.mongo.fetch_user(user)

        if user_data is None:
            ctx = await self.ctx.bot.get_application_context(interaction)

            await self.ctx.bot.handle_new_user(ctx)
            return

        if user_data.banned:
            return await interaction.response.send_message(
                "You are banned", ephemeral=True
            )

        if is_author is False and user.id in self.racers:
            return await interaction.response.send_message(
                "You are already in this race!", ephemeral=True
            )

        msg = (
            self.ctx.interaction.message
            or await self.ctx.interaction.original_message()
        )

        # If the author joins, the race starts

        if is_author and len(self.racers) <= 1:
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

            self.ctx.bot.active_start(user.id)

            self.racers[user.id] = RaceMember(user, user_data, interaction.response)

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

        race_users = [f"{r.user}" for r in self.racers.values()]

        raw_content = ", ".join(race_users)

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
        self.end_all_racers()

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
        self.ctx.bot.active_start(self.ctx.author.id)

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

    tt_group = SlashCommandGroup("tt", "Take a typing test")
    race_group = SlashCommandGroup(
        "race",
        f"Take a multiplayer typing test. Up to {MAX_RACE_JOIN-1} other users can join your race.",
    )

    def __init__(self, bot):
        self.bot = bot

    @cooldown(5, 1)
    @tt_group.command()
    async def dictionary(self, ctx, length: word_amt()):
        """Take a dictionary typing test"""
        quote_info = await self.handle_dictionary_input(ctx, length)

        await self.do_typing_test(ctx, True, quote_info, length, ctx.respond)

    @cooldown(5, 1)
    @tt_group.command()
    async def quote(self, ctx, length: quote_amt()):
        """Take a quote typing test"""
        quote_info = await self.handle_quote_input(length)

        await self.do_typing_test(ctx, False, quote_info, length, ctx.respond)

    @cooldown(6, 2)
    @race_group.command()
    async def dictionary(self, ctx, length: word_amt()):
        """Take a multiplayer dictionary typing test"""

        quote_info = await self.handle_dictionary_input(ctx, length)

        await self.show_race_start(ctx, True, quote_info)

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
        user = await ctx.bot.mongo.fetch_user(ctx.author)

        # Storing is_dict and quote in RaceJoinView because do_race method will be called inside it
        view = RaceJoinView(ctx, user, is_dict, *quote_info)
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

        base_img = get_base_img(raw_quote, wrap_width, user.theme)

        loading_img = get_loading_img(base_img, user.theme[1])

        file = save_img_as_discord_png(loading_img, "loading")

        embed.set_image(url="attachment://loading.png")
        embed.set_thumbnail(url="https://i.imgur.com/ZRfx4yz.gif")

        await send(embed=embed, file=file, delete_after=5)

        load_start = time.time()

        # Generating the acutal test image

        # TODO: generate pacer if the user has a pacer

        file = save_img_as_discord_png(base_img, "test")

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

        else:
            end_time = round(message.created_at.timestamp() - start_time, 2)

            return message, end_time, pacer_name, raw_quote

    @classmethod
    async def do_typing_test(cls, ctx, is_dict, quote_info, length, send):
        ctx.bot.active_start(ctx.author.id)

        quote, _ = quote_info

        user = await ctx.bot.mongo.fetch_user(ctx.author)

        # Prompting a captcha at intervals to prevent automated accounts
        if (user.test_amt + 1) % CAPTCHA_INTERVAL == 0:
            return await cls.handle_interval_captcha(ctx, user)

        result = await cls.personal_test_input(
            user, ctx, int(is_dict), quote_info, send
        )

        if result is None:
            ctx.bot.active_end(ctx.author.id)
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

        word_display = get_word_display(quote, raw_quote)

        embed = add_test_stats_to_embed(
            embed,
            wpm,
            raw,
            acc,
            end_time,
            len(u_input),
            cw,
            word_history,
            user.language,
            pacer_name,
            word_display,
            xp_earned,
        )

        view = TestResultView(ctx, user, is_dict, *quote_info, length)

        view.message = await message.reply(embed=embed, view=view, mention_author=False)

        ctx.bot.active_end(ctx.author.id)

        user = await ctx.bot.mongo.fetch_user(ctx.author)

        # For logging
        is_hs = False
        show_hs_captcha = False

        # Checking if there is a new high score

        user.test_amt += 1

        user.add_xp(xp_earned)
        user.add_words(cw)

        result = get_test_zone_name(cw)

        warning = get_test_warning(raw, acc, result)

        if warning is not None:
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
                is_race=False,
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

                is_hs = True

                if check <= wpm >= 100:
                    # Preventing on_application_command_completion from being invoked
                    ctx.no_completion = True

                    view = HighScoreCaptchaView(ctx, user, wpm)

                    await view.start()

                    show_hs_captcha = True

        if show_hs_captcha is False:
            await ctx.bot.mongo.replace_user_data(user, ctx.author)

        # Logging the test
        additional = get_log_additional(wpm, raw, acc, word_display, xp_earned)

        additional += f"\n**Word History:**\n> {word_history}"

        await cls.log_typing_test(ctx, "Typing Test", wpm, additional, is_hs)

    @staticmethod
    async def log_typing_test(ctx, name, wpm, additional: str, is_hs: bool):
        test_embed = get_log_embed(
            ctx,
            title=name,
            additional=additional,
        )

        embeds = [test_embed]

        if is_hs:
            hs_embed = test_embed.copy()
            hs_embed.title = "High Score"

            if wpm >= SUSPICIOUS_THRESHOLD:
                await ctx.bot.impt_wh.send(embed=hs_embed)

            embeds.append(hs_embed)

        await ctx.bot.test_wh.send(embeds=embeds)

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

        word_display = f"**Word:** {captcha_word}"

        # Evaluating the success of the captcha
        if message.content.lower() == captcha_word:
            embed = ctx.embed(
                title=f"{icons.success} Captcha Completed", add_footer=False
            )
            await ctx.respond(embed=embed)

            user.test_amt += 1

            await ctx.bot.mongo.replace_user_data(user, ctx.author)

            embed = get_log_embed(
                ctx, title="Interval Captcha Passed", additional=word_display
            )

        else:
            embed = ctx.error_embed(title=f"{icons.caution} Captcha Failed")

            await ctx.respond(embed=embed)

            embed = get_log_embed(
                ctx,
                title="Interval Captcha Failed",
                additional=word_display,
                error=False,
            )

        # Logging the captcha
        await ctx.bot.test_wh.send(embed=embed)


def setup(bot):
    bot.add_cog(Typing(bot))
