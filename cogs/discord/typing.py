import asyncio
import json
import math
import random
import textwrap
import time
from copy import copy
from datetime import datetime
from itertools import chain, groupby

import discord
import humanize
from captcha.image import ImageCaptcha
from discord.commands import SlashCommandGroup
from discord.ext import bridge, commands, tasks
from discord.utils import escape_markdown
from humanfriendly import format_timespan

import data.icons as icons
import word_list
from data.constants import (
    CAPTCHA_ACC_PERC,
    CAPTCHA_INTERVAL,
    CAPTCHA_STARTING_THRESHOLD,
    CAPTCHA_WPM_DEC,
    DEFAULT_WRAP,
    IMPOSSIBLE_THRESHOLD,
    MAX_CAPTCHA_ATTEMPTS,
    MAX_RACE_JOIN,
    MIN_PACER_SPEED,
    RACE_JOIN_EXPIRE_TIME,
    STATIC_IMAGE_FORMAT,
    SUPPORT_SERVER_INVITE,
    SUSPICIOUS_THRESHOLD,
    TEST_EXPIRE_TIME,
    TEST_LOAD_TIME,
    TEST_RANGE,
    TEST_ZONES,
)
from helpers.checks import cooldown
from helpers.image import (
    get_base_img,
    get_highscore_captcha_img,
    get_loading_img,
    get_pacer,
    get_raw_base_img,
    save_discord_static_img,
)
from helpers.ui import BaseView, ScrollView, create_link_view, get_log_embed
from helpers.user import get_pacer_display, get_pacer_speed
from helpers.utils import (
    cmd_run_before,
    copy_doc,
    estimate_placing,
    get_lb_display,
    get_test_stats,
    get_test_type,
    get_test_zone,
    get_test_zone_name,
    get_users_from_lb,
    get_xp_earned,
    invoke_completion,
    invoke_slash_command,
    message_banned_user,
)

# Spacing
THIN_SPACE = "\N{THIN SPACE}"
LONG_SPACE = "\N{IDEOGRAPHIC SPACE}"

LINE_SPACE = "\N{BOX DRAWINGS LIGHT HORIZONTAL}"

HIGH_SCORE_CAPTCHA_TIMEOUT = 60


def _load_test_file(name):
    with open(f"./word_list/{name}", "r", encoding="utf-8-sig") as f:
        data = json.load(f)

    return data["words"], data.get("wrap", DEFAULT_WRAP)


def _author_is_user(ctx):
    return lambda m: m.author.id == ctx.author.id


def _get_word_display(quote, raw_quote):
    return f"{len(quote)} ({len(raw_quote)} chars)"


async def _cheating_check(ctx, user, user_data, score, word_history):
    """Prevents blatant cheating"""
    if score.wpm >= IMPOSSIBLE_THRESHOLD:

        reason = "Cheating on the typing test"

        user_data = await ctx.bot.mongo.add_inf(ctx, user, user_data, reason)

        await ctx.bot.mongo.wipe_user(user_data)

        await message_banned_user(ctx, user, reason)

        embed = get_log_embed(
            ctx,
            title="Another Cheater Busted!!!",
            additional=(
                f"**Wpm:** {score.wpm}\n"
                f"**Raw:** {score.raw}\n"
                f"**Accuracy:** {score.acc}\n"
                f"**Word History:**\n> {word_history}"
            ),
            error=True,
            author=user,
        )

        await ctx.bot.impt_wh.send(embed=embed)

        return user_data

    return False


def _get_test_warning(raw, acc, result):
    if acc < 75:
        if raw > 300:
            return "Please try not to spam the test."
        return "Tests below 75% accuracy are not saved."

    if result is None:
        return "Tests below 10 correct words are not saved."

    return


def _get_user_input(message):
    return [] if message.content is None else message.content.split()


def _get_test_time(start: float, end: float):
    return max(round((start - end), 2), 0.01)


def _add_test_stats_to_embed(
    *,
    embed,
    wpm,
    raw,
    acc,
    end_time,
    mistakes,
    word_history,
    xp_earned=None,
    total_xp=None,
    show_thumbnail=True,
):
    embed.add_field(name=f"{icons.wpm} Wpm", value=wpm)
    embed.add_field(name=f"{icons.raw} Raw Wpm", value=raw)
    embed.add_field(name=f"{icons.acc} Accuracy", value=f"{acc}%")

    embed.add_field(name=f"{icons.time} Time", value=f"{end_time}s")

    if xp_earned is not None:
        embed.add_field(
            name=f"{icons.xp} Experience", value=f"{xp_earned} ({total_xp:,} total)"
        )

    embed.add_field(name=f"{icons.mistake} Mistakes", value=mistakes)

    if xp_earned is None:
        embed.add_field(name="** **", value="** **")

    embed.add_field(
        name="** **",
        value=f"**Word History**\n> {word_history}",
        inline=False,
    )

    if show_thumbnail:
        embed.set_thumbnail(url="https://i.imgur.com/l9sLfQx.png")

    return embed


def _add_test_settings_to_embed(embed, language, pacer_name, word_display):
    escape = "\U0000001b"

    colour_num = random.randint(31, 36)

    embed.add_field(
        name="** **",
        value=f"```ansi\n{escape}[1;2m{escape}[1;{colour_num}mTest Settings```\n** **",
        inline=False,
    )
    # Settings
    embed.add_field(name=f"{icons.language} Language", value=language.capitalize())
    embed.add_field(name=f"{icons.pacer} Pacer", value=pacer_name)
    embed.add_field(name=f"{icons.words} Words", value=word_display)

    return embed


class TournamentView(ScrollView):
    def __init__(self, ctx, raw_t_data):

        self.start_date = datetime.utcnow()

        self.t_data = self.sort_t_data(raw_t_data)

        # Caches the leaderboard data
        self.lb_data = None

        self.prev_view = None

        self.fetched = True

        # The current tournament index
        self.t_page = 0

        # The scroll view is used for scroll between the rankings in each tournament
        super().__init__(ctx, iter=self.get_iter, per_page=10, row=1)

    @property
    def total(self):
        return len(self.t.rankings)

    @property
    def t(self):
        return self.t_data[self.t_page]

    @property
    def t_max_page(self):
        return len(self.t_data)

    @property
    def user(self):
        return self.ctx.initial_user

    def get_iter(self):
        return self.lb_data

    def get_tournament_type(self, t):
        if t.end_time > self.start_date:
            return 0
        elif self.start_date < t.start_time:
            return 1
        else:
            return 2

    def sort_t_data(self, raw_t_data):
        # Ranking order: [soonest finish - latest finish, not started, finished]

        # Separating the tournaments into the three classifications in order that they will be shown in
        tournaments = [[], [], []]

        for t in raw_t_data:
            t_type = self.get_tournament_type(t)

            tournaments[t_type].append(t)

        # Grouping and sorting the tournaments by end time
        return sorted(sum(tournaments, []), key=lambda t: t.end_time, reverse=True)

    def get_placing(self, user_id: int):
        user_id = str(user_id)

        if user_id not in self.t.rankings:
            return None

        # Sorting the tournament data
        sorted_lb = dict(
            sorted(self.t.rankings.items(), key=lambda item: item[1], reverse=True)
        )

        placing_index = list(sorted_lb.keys()).index(user_id)

        score = sorted_lb[user_id]

        return placing_index, score

    async def do_tournament_test(self, _interaction):
        async def _test_callback(interaction):
            # Refetching the tournament data
            if self.fetched is False:

                self.start_date = datetime.utcnow()

                t_type = self.get_tournament_type(self.t)

                # Checking if the tournament is still active
                if t_type == 2:
                    await interaction.response.send_message(
                        "This tournament is now finished.", ephemeral=True
                    )

                raw_t_data = await self.ctx.bot.mongo.fetch_all_tournaments()

                self.t_data = self.sort_t_data(raw_t_data)

                self.lb_data = None

            if self.prev_view is not None:
                # Disabling the buttons if they were clicked
                await self.prev_view.disable_btn(self.prev_view.next_test)

            # The amount of words in each tournament test
            length = 30

            quote_info = await Typing.handle_dictionary_input(self.ctx, length)

            quote = quote_info[0]

            raw_quote = " ".join(quote)

            user = await self.ctx.bot.mongo.fetch_user(self.ctx.author)

            is_dict = True

            result = await Typing.personal_test_input(
                user,
                self.ctx,
                int(is_dict),
                quote_info,
                interaction.response.send_message,
            )

            if result is None:
                return

            message, end_time, *_ = result

            u_input = message.content.split()

            wpm, raw, acc, _, cw, word_history, wrong = get_test_stats(
                u_input, quote, end_time
            )

            # Sending the results
            embed = self.ctx.embed(
                title=f"{self.t.name} Tournament Test\n\n`Statistics`"
            )

            embed.set_author(
                name=self.ctx.author,
                icon_url=self.ctx.author.display_avatar.url,
            )

            embed = _add_test_stats_to_embed(
                embed=embed,
                wpm=wpm,
                raw=raw,
                acc=acc,
                end_time=end_time,
                mistakes=len(u_input) - cw,
                word_history=word_history,
                show_thumbnail=False,
            )

            embed.set_thumbnail(url=self.t.icon)

            view = TestResultView(self.ctx, user, is_dict, length)

            self.prev_view = view

            view.next_test.callback = _test_callback

            await message.reply(embed=embed, view=view, mention_author=False)

            # Creating the score object to manage the statistics better
            score = self.ctx.bot.mongo.Score(
                wpm=wpm,
                raw=raw,
                acc=acc,
                cw=cw,
                tw=len(quote),
                xp=0,
                timestamp=datetime.utcnow(),
                is_race=False,
                test_type_int=int(is_dict),
                wrong=wrong,
            )

            test_zone = get_test_zone_name(score.cw)

            warning = _get_test_warning(score.raw, score.acc, test_zone)

            # Checking if there are any warnings
            if warning is not None:
                await self.ctx.respond(f"Warning: {warning}", ephemeral=True)

            else:
                result = await _cheating_check(
                    self.ctx, self.ctx.author.id, user, score, word_history
                )

                if result:
                    # Saving the user ban
                    await self.ctx.bot.mongo.replace_user_data(user, result)

                else:
                    # Getting the tournament value of the score (the value that is going to be stored)
                    value = self.t.get_value(score)

                    # Save the result to the tournament
                    await self.ctx.bot.mongo.db.tournament.update_one(
                        {"_id": self.t.id},
                        {"$max": {f"rankings.{self.ctx.author.id}": value}},
                    )

                    # Estimating the new placing of the user in the tournament

                    placing = self.get_placing(self.ctx.author.id)

                    old_value = 0 if placing is None else placing[1]

                    sorted_values = list(sorted(self.t.rankings.values(), reverse=True))

                    estimate = estimate_placing(sorted_values, old_value, value)

                    if estimate is not None:

                        potential_placing, diff = estimate

                        if diff is not False:

                            placing = humanize.ordinal(potential_placing)

                            msg = f"Your tournament placing is now **{placing}"

                            if diff is not None:
                                msg += f" ({icons.up_arrow}{diff})"

                            msg += "**"

                            await self.ctx.respond(msg, ephemeral=True)

            word_display = _get_word_display(quote, raw_quote)

            additional = f"**Tournament Name**: {self.t.name}"

            await Typing.log_typing_test(
                self.ctx,
                "Tournament Test",
                score,
                word_display,
                word_history,
                additional=additional,
            )

            invoke_completion(self.ctx)

            self.fetched = False

        await _test_callback(_interaction)

    @discord.ui.button(row=2)
    async def start_btn(self, button, interaction):
        # Disabling the other buttons
        self.disable_all_items()

        await interaction.message.edit(view=self)

        await self.do_tournament_test(interaction)

    @discord.ui.button(label="Next Tournament", style=discord.ButtonStyle.primary)
    async def next_tournament(self, button, interaction):
        if self.t_page != 0:
            self.t_page -= 1
            await self.update_all(interaction)

    @discord.ui.button(label="Previous Tournament", style=discord.ButtonStyle.primary)
    async def prev_tournament(self, button, interaction):
        if self.t_page != self.t_max_page:
            self.t_page += 1
            await self.update_all(interaction)

    async def update_buttons(self):
        await super().update_buttons()

        # Updating the scrolling tournament page buttons

        self.next_tournament.disabled = self.t_page == 0
        self.prev_tournament.disabled = self.t_page == self.t_max_page - 1

        # Updating the join button

        t_type = self.get_tournament_type(self.t)

        if t_type == 0:
            self.start_btn.disabled = False
            self.start_btn.label = "Start"
            self.start_btn.style = discord.ButtonStyle.success
        else:
            self.start_btn.disabled = True
            self.start_btn.style = discord.ButtonStyle.grey

            if t_type == 1:
                self.start_btn.label = "Not Started"
            else:
                self.start_btn.label = "Finished"

    async def create_page(self):
        t_type = self.get_tournament_type(self.t)

        if t_type == 0:
            t_time = f"Ends in <t:{self.t.unix_end}:R> (<t:{self.t.unix_end}:f>)"
        elif t_type == 1:
            t_time = f"Starts in <t:{self.t.unix_start}:R> (<t:{self.t.unix_start}:f>)"
        else:
            t_time = f"Ended <t:{self.t.unix_end}:R> (<t:{self.t.unix_end}:f>)"

        if self.t.rankings and self.max_page > 1:
            page_display = f"(Page {self.page + 1} - {self.max_page})"
        else:
            page_display = ""

        if self.t.prizes is None:
            prizes = None

        elif len(self.t.prizes) == 1:
            prizes = f"**\n\nThe winner will receive {self.t.prizes [0]}.**"

        else:
            prizes = "\n\n**Prizes:**"

            for i, p in enumerate(self.t.prizes):
                prizes += f"\n{i + 1}. {p}"

        embed = self.ctx.embed(
            title=self.t.name,
            description=(
                f"{self.t.description}{prizes}\n\n"
                f"{self.t.rules}\n\n"
                f"{t_time}\n\n"
                f"**Rankings: {page_display}**"
            ),
            url=self.t.link,
        )

        # Displaying the rankings of the tournament
        if self.t.rankings:

            if self.lb_data is None:
                data = await get_users_from_lb(self.ctx.bot, self.t.rankings)

                self.lb_data = sorted(data, key=lambda x: x[1], reverse=True)

            for i, (u, v) in enumerate(self.items):

                placing = self.start_page + i + 1

                lb_display = get_lb_display(
                    placing, self.t.unit, u, v, self.ctx.author.id
                )

                prefix = self.t.get_ranking_prefix(placing, v)

                if prefix is not None:
                    lb_display = prefix + lb_display

                embed.add_field(
                    name=lb_display,
                    value="** **",
                    inline=False,
                )

            placing = self.get_placing(self.ctx.author.id)

            if placing is not None:
                placing_index, score = placing

                display = get_lb_display(
                    placing_index + 1, self.t.unit, self.user, score
                )

                prefix = self.t.get_ranking_prefix(placing_index + 1, v)

                if prefix is not None:
                    display = prefix + display

                embed.add_field(
                    name=f"{LINE_SPACE * 13}\n{display}",
                    value="** **",
                    inline=False,
                )

        else:
            embed.description += "\nNo users have participated yet"

        embed.set_thumbnail(url=self.t.icon)

        return embed


class RetryView(BaseView):
    def __init__(self, ctx, captcha_callback):
        super().__init__(ctx, timeout=HIGH_SCORE_CAPTCHA_TIMEOUT)

        self.captcha_callback = captcha_callback

    async def on_timeout(self):
        invoke_completion(self.ctx)

        await super().on_timeout()

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
        invoke_completion(self.ctx)

        await super().on_timeout()

    @property
    def target(self):
        return int(self.original_wpm * (1 - CAPTCHA_WPM_DEC))

    @discord.ui.button(label="Start Captcha", style=discord.ButtonStyle.success)
    async def start_captcha(self, button, interaction):
        await self.handle_captcha(self, button, interaction)

    async def log_captcha_completion(self, raw, acc, word_history, failed: bool):
        completion_type = "Fail" if failed else "Pass"

        embed = get_log_embed(
            self.ctx,
            title=f"High Score Captcha {completion_type}",
            additional=(
                f"**Original Wpm:** {self.original_wpm}\n"
                f"**Raw:** {raw} / {self.target}\n"
                f"**Acc:** {acc} / {CAPTCHA_ACC_PERC}\n"
                f"**Attempts:** {self.attempts} / {MAX_CAPTCHA_ATTEMPTS}\n"
                f"**Word History:**\n> {word_history}"
            ),
            error=failed,
        )

        await self.ctx.bot.test_wh.send(embed=embed)

        if failed and self.original_wpm >= SUSPICIOUS_THRESHOLD:
            await self.ctx.bot.impt_wh.send(embed=embed)

    async def handle_captcha(self, view, button, interaction):
        self.ctx.bot.active_start(self.ctx.author.id)

        button.disabled = True

        await interaction.message.edit(view=view)

        # Generating the quote for the test
        quote, wrap_width = await Typing.handle_dictionary_input(self.ctx, 35)

        raw_quote = " ".join(quote)

        base_img = await get_base_img(
            self.ctx.bot, raw_quote, wrap_width, self.user.theme
        )

        captcha_img = await get_highscore_captcha_img(
            self.ctx.bot, base_img, self.user.theme[1]
        )

        captcha_loading_img = await get_loading_img(
            self.ctx.bot, captcha_img, self.user.theme[1]
        )

        file = save_discord_static_img(captcha_loading_img, "captcha")

        # Generating the loading embed

        i_embed = self.ctx.embed(title=f"{self.ctx.author} | High Score Captcha")

        embed = copy(i_embed)

        i_embed.set_image(url=f"attachment://captcha.{STATIC_IMAGE_FORMAT}")
        i_embed.set_thumbnail(url="https://i.imgur.com/ZRfx4yz.gif")

        await interaction.response.send_message(
            embed=i_embed, file=file, delete_after=TEST_LOAD_TIME
        )

        load_start = time.time()

        file = save_discord_static_img(captcha_img, "test")

        # Generating the test embed

        embed.set_image(url=f"attachment://test.{STATIC_IMAGE_FORMAT}")

        load_time = time.time() - load_start

        await asyncio.sleep(TEST_LOAD_TIME - max(load_time, 0))

        start_lag = time.time()

        embed.description = f"\n**Started:** <t:{int(start_lag)}:R>"

        start_msg = await self.ctx.respond(embed=embed, file=file)

        lag = time.time() - start_lag

        tc = len(raw_quote)

        # Calculating the expire time based on the target wpm
        expire_time = (12 * tc) / self.target + 2

        finished_test = True

        try:
            message = await self.ctx.bot.wait_for(
                "message",
                check=_author_is_user(self.ctx),
                timeout=expire_time,
            )
        except asyncio.TimeoutError:
            raw = acc = word_history = None
            finished_test = False

        self.ctx.bot.active_end(self.ctx.author.id)

        if finished_test:
            end_time = _get_test_time(
                message.created_at.timestamp(), start_msg.created_at.timestamp() + lag
            )

            u_input = _get_user_input(message)

            _, raw, _, cc, _, word_history, _ = get_test_stats(u_input, quote, end_time)

            ratio = cc / len(" ".join(quote))

            acc = round(ratio * 100, 2)
            raw = round(raw * ratio, 2)

            # Checking if the test was passed
            if math.ceil(raw) >= self.target and acc >= CAPTCHA_ACC_PERC:
                embed = self.ctx.embed(
                    title="Passed", description="You passed the high score captcha!"
                )

                embed.add_field(
                    name=f"{icons.mistake} Attempts",
                    value=f"{self.attempts} / {MAX_CAPTCHA_ATTEMPTS}",
                )

                embed = self.add_results(embed, raw, acc, word_history)

                await self.ctx.respond(embed=embed)

                await self.ctx.bot.mongo.replace_user_data(self.user, self.ctx.author)

                invoke_completion(self.ctx)

                # Logging the pass of the high score captcha
                return await self.log_captcha_completion(raw, acc, word_history, False)

        self.attempts += 1

        attempts_left = MAX_CAPTCHA_ATTEMPTS - self.attempts

        embed = self.ctx.error_embed(title="Failed")

        if finished_test:
            embed = self.add_results(embed, raw, acc, word_history)

        if attempts_left == 0:
            embed.description = "You have no more attempts left"

            await self.ctx.respond(embed=embed)

            invoke_completion(self.ctx)

            return await self.log_captcha_completion(raw, acc, word_history, True)

        plural = "s" if attempts_left > 1 else ""

        embed.description = f"You have **{attempts_left}** attempt{plural} left."

        view = RetryView(self.ctx, self.handle_captcha)

        await self.ctx.respond(embed=embed, view=view)

        await self.log_captcha_completion(raw, acc, word_history, True)

    def add_results(self, embed, raw, acc, word_history):
        embed.add_field(name=f"{icons.raw} Raw Wpm", value=f"{raw} / {self.target}")

        embed.add_field(
            name=f"{icons.acc} Accuracy", value=f"{acc}% / {CAPTCHA_ACC_PERC}%"
        )

        embed.add_field(
            name="Word History", value=word_history or "** **", inline=False
        )

        return embed

    async def start(self):
        embed = self.ctx.embed(
            title=f"{self.ctx.author} | High Score Captcha",
            description=(
                f"You got a new high score of **{self.original_wpm}**!\n\n"
                "Please complete a short typing test captcha so we can make\n"
                "sure you aren't being dishonest.\n\n"
                "You won't have to take this test again until you beat your\n"
                f"new high score by **{int(CAPTCHA_WPM_DEC*100)}%**.\n\n"
                f"Type at least **{self.target}** raw wpm with **{CAPTCHA_ACC_PERC}%+** accuracy to pass."
            ),
        )

        await self.ctx.respond(embed=embed, view=self)


class TestResultView(BaseView):
    def __init__(self, ctx, user, is_dict, length):
        super().__init__(ctx)

        # Adding link buttons because they can't be added with a decorator
        self.add_item(discord.ui.Button(label="Join Server", url=SUPPORT_SERVER_INVITE))
        self.add_item(
            discord.ui.Button(label="Invite Bot", url=ctx.bot.create_invite_link())
        )

        # Settings of the test completed
        self.length = length
        self.is_dict = is_dict

        self.ctx.initial_user = user

    async def disable_btn(self, button):
        button.disabled = True

        await self.message.edit(view=self)

    @property
    def user(self):
        return self.ctx.initial_user

    async def get_user(self):
        self.ctx.initial_user = await self.ctx.bot.mongo.fetch_user(self.user.id)

    @discord.ui.button(label="Next Test", style=discord.ButtonStyle.success)
    async def next_test(self, button, interaction):
        await self.disable_btn(button)

        await self.get_user()

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


class TypingTestResultView(TestResultView):
    def __init__(self, ctx, user, is_dict, length, wrong, quote, wrap_width):
        super().__init__(ctx, user, is_dict, length)

        self.wrong = wrong

        self.quote = quote
        self.wrap_width = wrap_width

    @discord.ui.button(label="Practice Difficult", style=discord.ButtonStyle.primary)
    async def practice_test(self, button, interaction):
        await self.disable_btn(button)

        await self.get_user()

        if self.wrong == []:
            quote = self.quote

        else:
            words = set(self.wrong)
            quote_words = set(self.quote)

            minimum = min(4, len(quote_words))

            if (a := len(words)) < minimum:
                add_words = quote_words - words

                words |= set(random.sample(add_words, minimum - a))

            quote = random.choices(list(words), k=max(len(self.quote), 10))

        test_info = (quote, self.wrap_width)

        result = await Typing.personal_test_input(
            self.user, self.ctx, 2, test_info, interaction.response.send_message
        )

        if result is None:
            return

        message, end_time, pacer_name, raw_quote = result

        u_input = message.content.split()

        wpm, raw, acc, _, cw, word_history, _ = get_test_stats(u_input, quote, end_time)

        # Sending the results
        # Spacing in title keeps same spacing if word history is short
        embed = self.ctx.embed(
            title=f"Practice Test Results (Not Saved){THIN_SPACE*75}\n\n`Statistics`",
        )

        embed.set_author(
            name=self.ctx.author,
            icon_url=self.ctx.author.display_avatar.url,
        )

        word_display = _get_word_display(quote, raw_quote)

        embed = _add_test_stats_to_embed(
            embed=embed,
            wpm=wpm,
            raw=raw,
            acc=acc,
            end_time=end_time,
            mistakes=len(u_input) - cw,
            word_history=word_history,
        )

        embed = _add_test_settings_to_embed(
            embed,
            language=self.user.language,
            pacer_name=pacer_name,
            word_display=word_display,
        )

        await message.reply(embed=embed, mention_author=False)

        await self.ctx.respond("Warning: Practice tests are not saved")


class RaceMember:
    def __init__(self, user, data):
        # user object
        self.user = user

        # User's database document
        self.data = data

        # The test score (mongo.Score)
        self.result = None

        self.word_history = None

        self.save_score = True

        self.zone = None


class RaceEndView(BaseView):
    def __init__(self, ctx, callback):
        super().__init__(ctx)

        self.callback = callback

    @discord.ui.button(label="End Race Early", style=discord.ButtonStyle.danger)
    async def end_race(self, button, interaction):
        button.disabled = True

        await interaction.response.edit_message(view=self)

        self.callback()


class RaceJoinView(BaseView):
    def __init__(self, ctx, user, is_dict, quote, wrap_width):
        super().__init__(ctx, timeout=None, personal=False)

        self.user = user

        self.is_dict = is_dict
        self.quote = quote
        self.wrap_width = wrap_width

        self.racers = {}  # id: RaceMember (for preserve uniqueness)

        self.race_msg = None
        self.start_lag = None
        self.start_time = None

        # Cooldown for joining the race (prevents spamming join and leave)
        self.race_join_cooldown = commands.CooldownMapping.from_cooldown(
            1, 6, commands.BucketType.user
        )

        self.waiting_for_inputs = None

        self.add_author_to_race()

    @discord.ui.button(label="Join", style=discord.ButtonStyle.success)
    async def join_btn(self, button, interaction):
        await self.add_racer(interaction)

    @discord.ui.button(label="Leave", style=discord.ButtonStyle.danger)
    async def leave_btn(self, button, interaction):
        await self.remove_racer(interaction)

    def add_author_to_race(self):
        author = self.ctx.author

        race_member = RaceMember(author, self.user)
        self.racers[author.id] = race_member

    def end_all_racers(self):
        for r in self.racers:
            self.ctx.bot.active_end(r)

    async def remove_racer(self, interaction):
        user = interaction.user

        self.ctx.bot.active_end(user.id)

        # If the author leaves, the race is ended
        is_author = user.id == self.ctx.author.id

        if is_author:
            self.end_all_racers()

            embed = self.ctx.error_embed(
                title=f"{icons.caution} Race Ended",
                description="The race leader left the race",
            )

            await interaction.message.edit(embed=embed, view=None)
            return self.stop()

        if user.id not in self.racers:
            return await interaction.response.send_message(
                "You are not in the race!", ephemeral=True
            )

        del self.racers[user.id]

        embed = self.get_race_join_embed()

        await interaction.message.edit(embed=embed, view=self)

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

        if self.start_lag is not None:
            embed.description += f"\n**Started:** <t:{int(self.start_lag)}:R>"

        return embed

    def end_race_early(self):
        # Canceling the input tasks
        if self.waiting_for_inputs is not None:
            self.waiting_for_inputs.cancel()

        # Removing the active test remove all members
        for r in self.racers:
            self.ctx.bot.active_end(r)

    async def handle_racer_finish(self, m):
        self.ctx.bot.active_end(m.author.id)

        # Checking if it was the author who finished
        if m.author.id == self.ctx.author.id:
            # Prompting the author to end the test earlier
            end_view = RaceEndView(self.ctx, callback=self.end_race_early)

            await self.ctx.respond(content="", view=end_view, ephemeral=True)

        end_time = _get_test_time(m.created_at.timestamp(), self.start_time)

        r = self.racers[m.author.id]

        u_input = _get_user_input(m)

        wpm, raw, _, cc, cw, word_history, wrong = get_test_stats(
            u_input, self.quote, end_time
        )

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
            test_type_int=int(self.is_dict),
            wrong=wrong,
        )
        r.word_history = word_history

        embed = self.get_race_embed()
        embed.set_image(url=f"attachment://test.{STATIC_IMAGE_FORMAT}")

        await self.race_msg.edit(embed=embed)

    async def do_race(self, interaction):

        author_theme = self.racers[self.ctx.author.id].data.theme

        raw_quote = " ".join(self.quote)

        base_img = await get_base_img(
            self.ctx.bot, raw_quote, self.wrap_width, author_theme
        )

        loading_img = await get_loading_img(self.ctx.bot, base_img, author_theme[1])

        file = save_discord_static_img(loading_img, "loading")

        embed = self.get_race_embed()

        embed.set_image(url=f"attachment://loading.{STATIC_IMAGE_FORMAT}")
        embed.set_thumbnail(url="https://i.imgur.com/ZRfx4yz.gif")

        await interaction.response.send_message(
            embed=embed, file=file, delete_after=TEST_LOAD_TIME
        )

        load_start = time.time()

        file = save_discord_static_img(base_img, "test")

        load_time = time.time() - load_start

        await asyncio.sleep(TEST_LOAD_TIME - max(load_time, 0))

        self.start_lag = time.time()

        embed = self.get_race_embed()

        embed.set_image(url=f"attachment://test.{STATIC_IMAGE_FORMAT}")

        self.race_msg = await self.ctx.respond(embed=embed, file=file)

        lag = time.time() - self.start_lag

        self.start_time = self.race_msg.created_at.timestamp() + lag

        try:
            await asyncio.wait_for(
                self.wait_for_inputs(),
                timeout=TEST_EXPIRE_TIME,
            )
        except asyncio.TimeoutError:
            embed = self.ctx.error_embed(
                title="Race Ended",
                description=f"The race automatically ends after {format_timespan(TEST_EXPIRE_TIME)}",
            )

            await self.ctx.respond(embed=embed)

        await self.send_race_results()

    async def wait_for_inputs(self):
        # Handles the racer input for a single user
        async def handle_input(r):
            message = await self.ctx.bot.wait_for(
                "message", check=lambda m: m.author.id == r
            )

            try:
                await message.delete()
            except (discord.errors.Forbidden, discord.errors.NotFound):
                pass

            await self.handle_racer_finish(message)

        tasks = [asyncio.create_task(handle_input(r)) for r in self.racers]

        # Preventing input handling from blocking another
        self.waiting_for_inputs = asyncio.gather(*tasks)

        try:
            await self.waiting_for_inputs
        except asyncio.CancelledError:
            embed = self.ctx.error_embed(title="Race ended early by host")

            await self.ctx.respond(embed=embed)

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

            for r in g:
                score = r.result

                if r.result is None:
                    value = f"** **{LONG_SPACE}__Not Finished__"
                else:
                    value = (
                        f"** **{LONG_SPACE}{icons.wpm} Wpm: **{score.wpm}**\n"
                        f"{LONG_SPACE} {icons.raw} Raw Wpm: **{score.raw}**\n"
                        f"{LONG_SPACE} {icons.acc} Accuracy: **{score.acc}%**\n"
                        f"{LONG_SPACE} {icons.xp} Experience: **{score.xp} ({r.data.xp + score.xp} total)**"
                    )

                    test_zone = get_test_zone_name(score.cw)

                    warning = _get_test_warning(score.raw, score.acc, test_zone)

                    r.zone = test_zone

                    if warning is not None:
                        r.save_score = False
                        value += f"\n{LONG_SPACE} Warning: {warning}"

                    else:
                        result = await _cheating_check(
                            self.ctx, r.user, r.data, score, r.word_history
                        )

                        if result:
                            r.result = None
                            await self.ctx.bot.mongo.replace_user_data(result, r.user)

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

        word_display = _get_word_display(self.quote, raw_quote)

        race_size_display = f"**Race Size:** {len(self.racers)}"

        # Updating the users in the database
        for r in self.racers.values():
            score = r.result

            if score is None:
                break

            # Refetching user to account for state changes
            user = await self.ctx.bot.mongo.fetch_user(r.user)

            # Construction a context for each racer
            special_ctx = copy(self.ctx)
            special_ctx.other_author = r.user
            special_ctx.initial_user = r.data
            special_ctx.add_leaderboard_values()

            if r.save_score:

                user.add_score(score)
                user.add_words(score.cw)
                user.add_xp(score.xp)

            show_hs_captcha = False

            if r.zone is not None:
                zone, zone_range = r.zone

                score, show_hs_captcha = await Typing.handle_highscore_captcha(
                    ctx=special_ctx,
                    send=self.ctx.respond,
                    user=user,
                    score=score,
                    zone=zone,
                    zone_range=zone_range,
                )

            if show_hs_captcha is False:
                await self.ctx.bot.mongo.replace_user_data(user, r.user)

            # Invoking comnmand completion for the user
            special_ctx.is_slash = False
            invoke_completion(special_ctx)

            embed = await Typing.log_typing_test(
                special_ctx,
                "Race",
                score,
                word_display,
                r.word_history,
                additional=race_size_display,
                author=r.user,
                send=False,
            )

            embeds += embed

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

        if is_author:
            user_data = self.user
        else:
            user_data = await self.ctx.bot.mongo.fetch_user(user)

        # New users
        if user_data is None:
            ctx = await self.ctx.bot.get_application_context(interaction)

            await self.ctx.bot.handle_new_user(
                ctx, callback=self.add_racer, response=False
            )
            return

        # Banner users
        if user_data.banned:
            return await interaction.response.send_message(
                "You are banned!", ephemeral=True
            )

        # Users that are already in the race
        if is_author is False and user.id in self.racers:
            return await interaction.response.send_message(
                "You are already in this race!", ephemeral=True
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
            # the host of the race is the author of interaction.message by default
            fake_msg = interaction.message
            fake_msg.author = interaction.user

            bucket = self.race_join_cooldown.get_bucket(fake_msg)

            retry_after = bucket.update_rate_limit()

            if retry_after:
                timespan = format_timespan(retry_after)

                return await interaction.response.send_message(
                    f"Sorry, you are on cooldown, try again in {timespan}",
                    ephemeral=True,
                )

            self.ctx.bot.active_start(user.id)

            self.racers[user.id] = RaceMember(user, user_data)

        embed = self.get_race_join_embed(is_author)

        await self.ctx.edit(embed=embed, view=self)

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

        await self.ctx.edit(embed=embed, view=None)

    def get_race_join_embed(self, started=False):
        embed = self.ctx.embed(title="Typing Test Race", description="** **")

        users = self.get_formatted_users()

        if started:
            extra = "The race has started already! Be faster next time!"
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

        await self.ctx.respond(embed=embed, view=self)

        self.timeout_race.start()


class Typing(commands.Cog):
    """Typing test related commands"""

    emoji = "\N{KEYBOARD}"
    order = 2

    # Cache
    interval_captcha_fails = {}  # user_id: amt_in_a_row

    # Groups
    tt_group = SlashCommandGroup("tt", "Take a typing test")
    race_group = SlashCommandGroup(
        "race",
        f"Take a multiplayer typing test. Up to {MAX_RACE_JOIN-1} other users can join your race.",
    )

    # Arguments
    word_option = discord.option(
        name="length",
        type=int,
        desc=f"Choose a word amount from {TEST_RANGE[0]}-{TEST_RANGE[1]}",
    )

    quote_option = discord.option(
        name="length",
        type=str,
        desc="Choose a quote length",
        choices=TEST_ZONES.keys(),
    )

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @bridge.bridge_command()
    @cooldown(10, 3)
    async def tournaments(self, ctx):
        """Typing tournaments"""

        # Fetching the tournament data
        t_data = await self.bot.mongo.fetch_all_tournaments()

        if not t_data:
            embed = ctx.error_embed(title="Sorry, no tournaments found")

            return await ctx.respond(embed=embed)

        view = TournamentView(ctx, t_data)

        await view.start()

    @tt_group.command(name="dictionary")
    @cooldown(5, 1)
    @word_option
    async def tt_dictionary(self, ctx, length: int):
        """Take a dictionary typing test"""
        quote_info = await self.handle_dictionary_input(ctx, length)

        await self.do_typing_test(ctx, True, quote_info, length, ctx.respond)

    @tt_group.command(name="quote")
    @cooldown(5, 1)
    @quote_option
    async def tt_quote(self, ctx, length: str):
        """Take a quote typing test"""
        quote_info = await self.handle_quote_input(length)

        await self.do_typing_test(ctx, False, quote_info, length, ctx.respond)

    @commands.group(usage="[length]", invoke_without_command=True)
    @cooldown(5, 1)
    @copy_doc(tt_dictionary)
    async def tt(self, ctx, length: int = 35):
        await invoke_slash_command(self.tt_dictionary, self, ctx, length)

    @tt.command(usage="[length]", name="quote")
    @cooldown(5, 1)
    @copy_doc(tt_quote)
    async def _tt_quote(self, ctx, length: str):
        await invoke_slash_command(self.tt_quote, self, ctx, length)

    @race_group.command(name="dictionary")
    @cooldown(6, 2)
    @word_option
    async def race_dictionary(self, ctx, length: int = 35):
        """Take a multiplayer dictionary typing test"""

        quote_info = await self.handle_dictionary_input(ctx, length)

        await self.show_race_start(ctx, True, quote_info)

    @race_group.command(name="quote")
    @cooldown(6, 2)
    @quote_option
    async def race_quote(self, ctx, length: str):
        """Take a multiplayer quote typing test"""

        quote_info = await self.handle_quote_input(length)

        await self.show_race_start(ctx, False, quote_info)

    @commands.group(usage="[length]", invoke_without_command=True)
    @cooldown(6, 2)
    @copy_doc(race_dictionary)
    async def race(self, ctx, length: int):
        await invoke_slash_command(self.race_dictionary, self, ctx, length)

    @race.command(usage="[length]", name="quote")
    @cooldown(6, 2)
    @copy_doc(race_quote)
    async def _race_quote(self, ctx, length: str):
        await invoke_slash_command(self.race_quote, self, ctx, length)

    @staticmethod
    async def handle_dictionary_input(ctx, length: int):
        if length not in range(TEST_RANGE[0], TEST_RANGE[1] + 1):
            raise commands.BadArgument(
                f"The typing test must be between {TEST_RANGE[0]} and {TEST_RANGE[1]} words"
            )

        user = ctx.initial_user

        words, wrap = _load_test_file(word_list.languages[user.language][user.level])

        return random.sample(words, length), wrap

    @staticmethod
    async def handle_quote_input(length: str):
        lower_options = {t.lower(): v for t, v in TEST_ZONES.items()}

        if length.lower() not in lower_options:
            raise commands.BadArgument(
                "Quote length must be in: " + ", ".join(TEST_ZONES.keys())
            )

        quotes, wrap = _load_test_file("quotes.json")

        # Getting the maximum amount of words for that test zone
        max_words = TEST_ZONES[length.lower()][-1]

        # Selecting consecutive items from list of sentences within max word amount
        start = random.randint(0, len(quotes))

        words = []

        last = None

        while (
            last is None or len(last) + len(joined := list(chain(*words))) <= max_words
        ):
            if last is not None:
                words.append(last)

            last = quotes[(len(words) + start) % len(quotes)].split()

        return joined, wrap

    @staticmethod
    async def show_race_start(ctx, is_dict, quote_info):
        # Storing is_dict and quote in RaceJoinView because do_race method will be called inside it
        view = RaceJoinView(ctx, ctx.initial_user, is_dict, *quote_info)
        await view.start()

        user = await ctx.bot.mongo.fetch_user(ctx.author)

        # Context tutorial
        if not cmd_run_before(ctx, user):
            await ctx.respond("Start the race by joining it", ephemeral=True)

    @staticmethod
    async def personal_test_input(user, ctx, test_type_int, quote_info, send):
        ctx.bot.active_start(ctx.author.id)

        quote, wrap_width = quote_info

        # Loading embed

        word_count = len(quote)

        test_type = get_test_type(test_type_int, word_count)

        test_zone = get_test_zone(word_count)

        if test_zone is not None:
            test_zone, _ = test_zone

        pacer = get_pacer_speed(user, test_zone)

        if pacer is False:
            pacer_name = f"N/A (Pacer below minium of {MIN_PACER_SPEED} wpm)"

        else:
            pacer_name = get_pacer_display(user.pacer_type, user.pacer_speed, pacer)

        title = f"{user.display_name} | {test_type} Test ({word_count} words)"

        # WOW THIS IS SUCH GREAT CODING :IOJ:FOWIJEFOW 10/10
        name = None if pacer_name is None else pacer_name.replace("\n", " ")

        desc = f"**Pacer:** {name}"

        embed = ctx.embed(
            title=title,
            description=desc,
            add_footer=False,
        )

        if pacer:
            embed.set_footer(text="Test time is adjusted for image load time")

        raw_quote = " ".join(quote)

        base_img, word_list = await get_raw_base_img(
            ctx.bot, raw_quote, wrap_width, user.theme
        )

        loading_img = await get_loading_img(ctx.bot, base_img, user.theme[1])

        file = save_discord_static_img(loading_img, "loading")

        embed.set_image(url=f"attachment://loading.{STATIC_IMAGE_FORMAT}")
        embed.set_thumbnail(url="https://i.imgur.com/ZRfx4yz.gif")

        await send(embed=embed, file=file, delete_after=TEST_LOAD_TIME)

        load_start = time.time()

        # Generating the acutal test image

        if pacer:

            buffer = await get_pacer(
                ctx.bot,
                base_img,
                user.theme[1],
                quote,
                word_list,
                pacer,
                user.pacer_type,
            )

            file = discord.File(buffer, filename="test.gif")

            image_format = "gif"
        else:
            file = save_discord_static_img(base_img, "test")
            image_format = STATIC_IMAGE_FORMAT

        embed = ctx.embed(title=title, add_footer=False)

        embed.set_image(url=f"attachment://test.{image_format}")

        # Waiting for remaining time

        load_time = time.time() - load_start

        await asyncio.sleep(TEST_LOAD_TIME - max(load_time, 0))

        start_lag = time.time()

        desc += f"\n**Started:** <t:{int(start_lag)}:R>"

        embed.description = desc

        send_msg = await ctx.respond(embed=embed, file=file)

        lag = time.time() - start_lag

        if not cmd_run_before(ctx, user):
            await ctx.respond("Type the text above!", ephemeral=True)

        # Waiting for the input from the user

        try:
            message = await ctx.bot.wait_for(
                "message",
                check=_author_is_user(ctx),
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
            return

        else:
            end_time = _get_test_time(
                message.created_at.timestamp(), send_msg.created_at.timestamp() + lag
            )

            return message, end_time, pacer_name, raw_quote

        finally:
            ctx.bot.active_end(ctx.author.id)

    @classmethod
    async def do_typing_test(cls, ctx, is_dict, quote_info, length, send):
        quote = quote_info[0]

        user = await ctx.bot.mongo.fetch_user(ctx.author)

        # Prompting a captcha at intervals to prevent automated accounts
        if (user.test_amt + 1) % CAPTCHA_INTERVAL == 0:
            return await cls.handle_interval_captcha(ctx, user, is_dict, length, send)

        result = await cls.personal_test_input(
            user, ctx, int(is_dict), quote_info, send
        )

        if result is None:
            return

        message, end_time, pacer_name, raw_quote = result

        # Evaluating the input of the user
        u_input = message.content.split()

        wpm, raw, acc, cc, cw, word_history, wrong = get_test_stats(
            u_input, quote, end_time
        )

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

        word_display = _get_word_display(quote, raw_quote)

        user = await ctx.bot.mongo.fetch_user(ctx.author)

        # Adding some stats
        user.test_amt += 1

        user.add_xp(xp_earned)
        user.add_words(cw)

        embed = _add_test_stats_to_embed(
            embed=embed,
            wpm=wpm,
            raw=raw,
            acc=acc,
            end_time=end_time,
            mistakes=len(u_input) - cw,
            word_history=word_history,
            xp_earned=xp_earned,
            total_xp=user.xp,
        )

        embed = _add_test_settings_to_embed(
            embed,
            language=user.language,
            pacer_name=pacer_name,
            word_display=word_display,
        )

        view = TypingTestResultView(ctx, user, is_dict, length, wrong, *quote_info)

        await message.reply(embed=embed, view=view, mention_author=False)

        # For logging
        show_hs_captcha = False

        # Checking if there is a new high score

        result = get_test_zone_name(cw)

        warning = _get_test_warning(raw, acc, result)

        score = ctx.bot.mongo.Score(
            wpm=wpm,
            raw=raw,
            acc=acc,
            cw=cw,
            tw=len(quote),
            xp=xp_earned,
            timestamp=datetime.utcnow(),
            is_race=False,
            test_type_int=int(is_dict),
            wrong=wrong,
        )

        if warning is not None:
            await ctx.respond(f"Warning: {warning}", ephemeral=True)

        else:
            zone, zone_range = result

            result = await _cheating_check(ctx, ctx.author, user, score, word_history)

            if result:
                user = result

            else:
                user.add_score(score)

                score, show_hs_captcha = await cls.handle_highscore_captcha(
                    ctx=ctx,
                    send=ctx.respond,
                    user=user,
                    score=score,
                    zone=zone,
                    zone_range=zone_range,
                )

        if show_hs_captcha is False:
            await ctx.bot.mongo.replace_user_data(user, ctx.author)

        # Logging the test

        await cls.log_typing_test(ctx, "Typing Test", score, word_display, word_history)

    @staticmethod
    async def log_typing_test(
        ctx,
        name,
        score,
        word_display,
        word_history,
        additional=None,
        author=None,
        send=True,
    ):

        stats = (
            f"**Wpm:** {score.wpm}\n"
            f"**Raw:** {score.raw}\n"
            f"**Accuracy:** {score.acc}\n"
            f"**Word Amount:** {word_display}\n"
            f"**XP:** {score.xp}\n"
            f"**Word History:**\n> {word_history}"
        )

        if additional is not None:
            stats += f"\n{additional}"

        test_embed = get_log_embed(ctx, title=name, additional=stats, author=author)

        embeds = [test_embed]

        if score.is_hs:
            hs_embed = test_embed.copy()
            hs_embed.title = "High Score"

            if score.wpm >= SUSPICIOUS_THRESHOLD:
                await ctx.bot.impt_wh.send(embed=hs_embed)

            embeds.append(hs_embed)

        if send is False:
            return embeds

        await ctx.bot.test_wh.send(embeds=embeds)

    @staticmethod
    async def handle_highscore_captcha(ctx, send, user, score, zone, zone_range):
        if score.wpm > user.highspeed[zone].wpm:
            prev_hs = user.highest_speed

            score.is_hs = True

            user.highspeed[zone] = score

            description = f"You got a new high score of **{score.wpm}** on the **{zone} test** {zone_range}"

            # Getting the user's placing for that zone
            c = ctx.bot.lbs[3].stats[list(TEST_ZONES.keys()).index(zone)]

            initial_value = c.get_initial_value(ctx)

            score_lb = await c.get_lb_values_from_score(max="inf", min=initial_value)

            estimate = estimate_placing(score_lb, initial_value, score.wpm)

            if estimate is not None:
                potential_placing, diff = estimate

                if diff is None:
                    diff_display = ""
                else:
                    diff_display = f" ({icons.up_arrow}{diff})"

                description += f"\n\nAlltime Placing: **{humanize.ordinal(potential_placing)}{diff_display}**"

            embed = ctx.embed(
                title=f":trophy: {user.display_name} | New High Score",
                description=description,
            )

            await send(embed=embed)

            # Test high score anti cheat system
            if (
                prev_hs * (1 + CAPTCHA_WPM_DEC)
                <= score.wpm
                >= CAPTCHA_STARTING_THRESHOLD
            ):
                # Preventing on_application_command_completion from being invoked
                ctx.no_completion = True

                view = HighScoreCaptchaView(ctx, user, score.wpm)

                await view.start()

                return score, True

        return score, False

    @classmethod
    async def handle_interval_captcha(cls, ctx, user, is_dict, length, send):
        ctx.bot.active_start(ctx.author.id)

        # Getting the quote for the captcha
        words, _ = _load_test_file(word_list.languages["english"]["easy"])
        captcha_word = random.choice(words)

        # Generating the captcha image
        image = ImageCaptcha(width=200)
        buffer = image.generate(captcha_word)
        buffer.seek(0)

        embed = ctx.embed(
            title=":robot: Captcha", description="Type the word below", add_footer=False
        )

        file = discord.File(fp=buffer, filename=f"captcha.{STATIC_IMAGE_FORMAT}")

        embed.set_image(url=f"attachment://captcha.{STATIC_IMAGE_FORMAT}")

        await send(embed=embed, file=file)

        # Waiting for user input
        try:
            message = await ctx.bot.wait_for(
                "message", check=_author_is_user(ctx), timeout=120
            )
        except asyncio.TimeoutError:
            embed = ctx.error_embed(
                title="Captcha Expired",
                description="You did not complete the captcha within 2 minutes",
            )
            await ctx.respond(embed=embed)
            return

        finally:
            ctx.bot.active_end(ctx.author.id)

        word_display = f"**Word:** {captcha_word}"

        flag_embed = None

        # Evaluating the success of the captcha
        if (
            message.content is not None
            and message.content.lower() == captcha_word.lower()
        ):
            result_embed = ctx.embed(
                title=f"{icons.success} Captcha Completed", add_footer=False
            )

            user.test_amt += 1

            await ctx.bot.mongo.replace_user_data(user, ctx.author)

            embed = get_log_embed(
                ctx, title="Interval Captcha Passed", additional=word_display
            )

        else:
            result_embed = ctx.error_embed(title=f"{icons.caution} Captcha Failed")

            embed = get_log_embed(
                ctx,
                title="Interval Captcha Failed",
                additional=word_display,
                error=True,
            )

            # Handling the fail

            fails = cls.interval_captcha_fails.get(ctx.author.id, 0) + 1

            cls.interval_captcha_fails[ctx.author.id] = fails

            if fails != 0 and fails % 5 == 0:
                flag_embed = get_log_embed(
                    ctx,
                    title="Several Consecutive Interval Captcha Fails",
                    additional=f"**Fails:** {fails}",
                    error=True,
                )

        view = TestResultView(ctx, user, is_dict, length)

        await message.reply(embed=result_embed, view=view, mention_author=False)

        # Logging the captcha
        await ctx.bot.test_wh.send(embed=embed)

        # Logging suspicious amount of fails
        if flag_embed is not None:
            await ctx.bot.impt_wh.send(embed=flag_embed)


def setup(bot):
    bot.add_cog(Typing(bot))
