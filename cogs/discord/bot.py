import csv
import json
import math
import time
from base64 import b64encode
from datetime import datetime, timezone
from io import BytesIO, StringIO

import discord
import humanize
from cryptography.fernet import Fernet
from discord.ext import bridge, commands

import icons
from challenges.achievements import categories, get_achievement_display
from challenges.daily import get_daily_challenges
from challenges.season import get_season_tiers
from config import GRAPH_CDN_SECRET
from constants import (
    COMPILE_INTERVAL,
    GRAPH_CDN_BASE_URL,
    GRAPH_EXPIRE_TIME,
    LB_DISPLAY_AMT,
    LB_LENGTH,
    PREMIUM_LINK,
    PREMIUM_SCORE_LIMIT,
    REGULAR_SCORE_LIMIT,
)
from helpers.checks import cooldown, user_check
from helpers.converters import user_option
from helpers.ui import BaseView, DictButton, ScrollView, ViewFromDict
from helpers.user import get_pacer_display, get_theme_display, get_typing_average
from helpers.utils import calculate_score_consistency, cmd_run_before, get_bar
from static.badges import get_badge_from_id

THIN_SPACE = "\N{THIN SPACE}"
LINE_SPACE = "\N{BOX DRAWINGS LIGHT HORIZONTAL}"

SCORE_DATA_LABELS = {
    "Wpm": "wpm",
    "Raw Wpm": "raw",
    "Accuracy": "acc",
    "Correct Words": "cw",
    "Total Words": "tw",
    "Experience": "xp",
    "Unix Timestamp": "unix_timestamp",
}

SCORES_PER_PAGE = 3

EMOJIS_PER_TIER = 4


def _encrypt_data(data: dict):
    encoded_data = b64encode(json.dumps(data).encode())

    encrypted_data = Fernet(GRAPH_CDN_SECRET.encode()).encrypt(encoded_data)

    return encrypted_data.decode()


def get_graph_link(*, user, amt: int, dimensions: tuple, current_time=None):
    if current_time is None:
        current_time = time.time()

    values = [[], [], []]

    for s in user.scores[-amt:]:
        values[0].append(s.wpm)
        values[1].append(s.raw)
        values[2].append(s.acc)

    labels = ["Wpm", "Raw Wpm", "Accuracy"]

    y_values = dict(zip(labels, values))

    payload = {
        "fig_size": dimensions,
        "until": current_time + GRAPH_EXPIRE_TIME,
        "y_values": y_values,
        "colours": user.theme + ["#ffffff"],
    }

    data = _encrypt_data(payload)

    return f"{GRAPH_CDN_BASE_URL}/score_graph?raw_data={data}"


class SeasonView(ViewFromDict):
    def __init__(self, ctx):
        categories = {
            "Information": self.get_info_embed,
            "Rewards": self.get_reward_embed,
        }

        super().__init__(ctx, categories)

    @property
    def user(self):
        return self.ctx.initial_user

    async def get_info_embed(self):
        embed = self.ctx.embed(title="Season Information")

        info = {
            "What are seasons?": "Seasons are a month-long competition open to all wordPractice users. Users compete to earn the most XP before the end of the season to earn exclusive prizes.",
            "How do I earn XP?": f"XP {icons.xp} can be earned through completing typing tests, daily challenges, voting and much more.",
            "What are season rewards?": "By completing seasonal challenges, users can win exclusive badges.",
            "How do I view the season leaderboads?": "The season leaderboard can be viewed with `/leaderboard` under the season category.",
        }

        for i, (title, desc) in enumerate(info.items()):
            spacing = "** **\n" if i != 0 else ""

            embed.add_field(name=f"{spacing}{title}", value=desc, inline=False)

        embed.set_thumbnail(url="https://i.imgur.com/0Mzb6Js.png")

        return embed

    async def get_reward_embed(self):
        embed = self.ctx.embed(
            title="Season Rewards",
            description=(
                "Unlock seasonal badges as you earn XP\n\n"
                f"{icons.xp} **{self.user.xp:,} XP**\n\n"
            ),
        )

        challenges = [v async for v in get_season_tiers(self.ctx.bot)]

        if challenges == []:
            embed.description = "Sorry, there are no rewards available..."
        else:

            p = self.user.xp / challenges[-1][0]

            bar = get_bar(
                p, size=EMOJIS_PER_TIER * len(challenges), variant=2, split=True
            )

            for i, (amt, r) in enumerate(challenges):
                emoji = (
                    icons.green_dot
                    if self.user.last_season_value >= amt
                    else icons.red_dot
                )

                index = (i + 1) * EMOJIS_PER_TIER - 1

                bar[index] += f"{emoji}**{r.badge_format()}** *{amt/1000:g}k*"

            embed.description += "\n".join(bar)

        return embed

    async def create_page(self):
        return await self.the_dict[self.page]()


class GraphButton(DictButton):
    def __init__(self, is_premium, **kwargs):
        self.is_premium = is_premium

        super().__init__(**kwargs)

    def toggle_eligible(self, value):
        if self.is_premium is False and value >= REGULAR_SCORE_LIMIT:
            self.disabled = True


class GraphView(ViewFromDict):
    def __init__(self, ctx, user):
        test_amts = [10, 25, 50, 100]

        super().__init__(ctx, {f"{i} Tests": i for i in test_amts})

        self.user = user

        self.current_time = time.time()

    def button(self, **kwargs):
        return GraphButton(self.user.is_premium, **kwargs)

    async def create_page(self):
        amt = self.the_dict[self.page]

        embed = self.ctx.embed(
            title=f"Last {amt} Scores", add_footer=self.user.is_premium
        )

        wpm, raw, acc, cw, tw, scores = get_typing_average(self.user, amt)

        # Getting the best score
        highest = max(scores, key=lambda x: x.wpm)
        lowest = min(scores, key=lambda x: x.wpm)

        embed.add_field(
            name="`Average`",
            value=(
                f"**Wpm:** {wpm}\n"
                f"**Raw Wpm:** {raw}\n"
                f"**Accuracy:** {acc}% ({cw} / {tw})"
            ),
            inline=True,
        )

        embed.add_field(name="`Best`", value=f"**Wpm:** {highest.wpm}", inline=True)

        embed.add_field(name="`Lowest`", value=f"**Wpm:** {lowest.wpm}", inline=True)

        url = get_graph_link(
            user=self.user, amt=amt, dimensions=(6, 4), current_time=self.current_time
        )

        if self.user.is_premium is False:
            embed.set_footer(text="Donators can save up to 250 tests")

        embed.set_image(url=url)

        return embed


class ScoreView(ScrollView):
    def __init__(self, ctx, user):
        page_amt = math.ceil(len(user.scores) / SCORES_PER_PAGE)

        super().__init__(ctx, page_amt, compact=page_amt < 7)

        self.user = user

    def get_formatted_data(self):
        data = {n: [] for n in SCORE_DATA_LABELS.keys()}

        for s in self.user.scores:
            for n, v in SCORE_DATA_LABELS.items():
                data[n].append(getattr(s, v))

        return data

    async def send_as_file(self, buffer, ext, button, interaction):
        file = discord.File(fp=buffer, filename=f"scores.{ext}")

        await interaction.response.send_message(file=file)

        button.disabled = True

        msg = await self.ctx.interaction.original_message()

        await msg.edit(view=self)

    @discord.ui.button(label="Download as CSV", style=discord.ButtonStyle.grey, row=1)
    async def csv_download(self, button, interaction):
        data = self.get_formatted_data()

        buffer = StringIO()

        writer = csv.writer(buffer)

        writer.writerow(data.keys())
        writer.writerows(zip(*data.values()))

        buffer.seek(0)

        await self.send_as_file(buffer, "csv", button, interaction)

    @discord.ui.button(label="Download as JSON", style=discord.ButtonStyle.grey, row=1)
    async def json_download(self, button, interaction):
        data = self.get_formatted_data()

        buffer = BytesIO()

        buffer.write(json.dumps(data).encode())

        buffer.seek(0)

        await self.send_as_file(buffer, "json", button, interaction)

    async def create_page(self):
        total_scores = len(self.user.scores)

        start_page = self.page * SCORES_PER_PAGE
        end_page = min((self.page + 1) * SCORES_PER_PAGE, total_scores)

        embed = self.ctx.embed(
            title=f"{self.user.display_name} | Recent Scores ({start_page + 1} - {end_page} of {total_scores})",
            description=" "
            if self.user.is_premium
            else f"**[Donators]({PREMIUM_LINK})** can download test scores",
        )

        for i, s in enumerate(self.user.scores[::-1][start_page:end_page]):
            timestamp = s.unix_timestamp

            embed.add_field(
                name=f"Score {start_page + i + 1} ({s.test_type})",
                value=(
                    f">>> **Wpm:** {s.wpm}\n"
                    f"**Raw:** 108.21 {s.raw}\n"
                    f"**Accuracy:** {s.acc}% ({s.cw} / {s.tw})\n"
                    f"**XP:** {s.xp}\n"
                    f"**Timestamp:** <t:{timestamp}:R>"
                ),
                inline=False,
            )
        return embed

    async def start(self):
        if self.user.is_premium is False:
            self.csv_download.disabled = True
            self.json_download.disabled = True

        await super().start()


class LeaderboardSelect(discord.ui.Select):
    def __init__(self, ctx):
        super().__init__(
            placeholder="Select a category...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=lb.title,
                    emoji=lb.emoji,
                    description=lb.desc,
                    value=str(i),
                )
                for i, lb in enumerate(ctx.bot.lbs)
            ],
            row=0,
        )

    async def callback(self, interaction):
        value = int(self.values[0])

        self.view.page = 0
        self.view.category = value
        self.view.placing = None

        self.view.stat = self.view.lb.default

        await self.view.update_all(interaction)


class LeaderboardButton(discord.ui.Button):
    def __init__(self, stat):
        super().__init__(row=1)

        self.stat = stat

    async def callback(self, interaction):
        await self.view.change_stat(interaction, self.stat)


class LeaderboardView(ScrollView):
    def __init__(self, ctx, user):
        super().__init__(ctx, int(LB_DISPLAY_AMT / 10), row=2, compact=True)

        self.timeout = 60

        self.user = user

        self.category = 1  # Starting on season category

        self.stat = self.lb.default

        # For storing placing across same page
        self.placing = None

        self.active_btns = []

    @property
    def lb(self):
        return self.ctx.bot.lbs[self.category]

    async def create_page(self):
        c = self.lb.stats[self.stat]

        time_until_next_update = int(
            self.ctx.bot.last_lb_update + COMPILE_INTERVAL * 60
        )

        embed = self.ctx.embed(
            title=f"{self.lb.title} Leaderboard | Page {self.page + 1}",
            description=f"The leaderboard updates again in <t:{time_until_next_update}:R>",
        )

        for i, u in enumerate(c.data[self.page * 10 : (self.page + 1) * 10]):
            p = self.page * 10 + i

            extra = ""

            if self.placing is None and u["_id"] == self.user.id:
                self.placing = p, u
                extra = "__"

            badge_icon = get_badge_from_id(u["status"])

            username = f"{u['name']}#{u['discriminator']} {badge_icon}"

            embed.add_field(
                name=f"`{p + 1}.` {extra}{username} - {u['count']} {c.unit}{extra}",
                value="** **",
                inline=False,
            )

        if self.placing is None:
            # Getting the placing
            self.placing = c.get_placing(self.user.id)

        if self.placing is None:
            place_display = "N/A"
            count = c.get_stat(self.user)

        else:
            place_display = self.placing[0] + 1
            count = self.placing[1]["count"]

        embed.add_field(
            name=f"{LINE_SPACE * 13}\n`{place_display}.` {self.user.display_name} - {count} {c.unit}",
            value="** **",
            inline=False,
        )

        return embed

    async def jump_to_placing(self, interaction):
        if self.placing is None:
            return await interaction.response.send_message(
                f"You are outside of the top {LB_DISPLAY_AMT}", ephemeral=True
            )

        # Getting the page where the user is placed
        page = int((self.placing[0] - 1) / 10)

        if self.page != page:
            self.page = page
            await self.update_all(interaction)

    async def change_stat(self, interaction, stat):
        """
        For changing the page in the metric button callbacks
        """
        if self.stat != stat:
            self.stat = stat
            self.page = 0
            self.placing = None

            await self.update_all(interaction)

    def get_active_btns(self):
        return [c for c in self.children if c.row == 1]

    def add_metric_buttons(self):
        metrics = [s.name for s in self.lb.stats]

        active_btns = self.get_active_btns()

        metric_amt = len(metrics)
        active_amt = len(active_btns)

        # Removing any extra buttons
        if active_amt > metric_amt:
            for c in active_btns[metric_amt:]:
                self.remove_item(c)

        # Adding any buttons
        elif active_amt < metric_amt:
            for i in range(len(metrics[active_amt:])):
                btn = LeaderboardButton(i + active_amt)

                self.add_item(btn)

        # Renaming and changing colour of buttons
        active_btns = self.get_active_btns()

        for i, c in enumerate(self.get_active_btns()):
            c.label = metrics[i]
            c.style = (
                discord.ButtonStyle.success
                if i == self.stat
                else discord.ButtonStyle.primary
            )

    async def update_buttons(self):
        # Updating the scrolling buttons
        await super().update_buttons()

        # Adding the correct metric buttons
        self.add_metric_buttons()

    async def start(self):
        # Cannot user decorator because it's added before scroll items are added and they are on the same row
        btn = discord.ui.Button(
            label="Jump to Placing",
            style=discord.ButtonStyle.grey,
            row=2,
        )
        btn.callback = self.jump_to_placing

        self.add_item(btn)

        select = LeaderboardSelect(self.ctx)
        self.add_item(select)

        await super().start()


class ProfileView(BaseView):
    def __init__(self, ctx, user):
        super().__init__(ctx)

        self.user = user
        self.callbacks = self.get_embed_callbacks()
        self.page = list(self.callbacks.keys())[0]

    async def update_message(self, interaction):
        embed = self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    def get_embed(self):
        """Generates the base embed for all the pages"""
        base_embed = self.get_base_embed(self.page)

        return self.callbacks[self.page][1](base_embed)

    def get_base_embed(self, page_name):
        embed = self.ctx.embed(title=self.user.display_name)
        embed.set_author(
            name=f"{self.user.username} | {page_name}",
            icon_url=self.user.avatar_url,
        )
        return embed

    def get_perc_sign(self, value: int, percs: tuple[int, int]):
        first, second = percs

        if value in range(0, int(first)):
            return "-"

        if value in range(int(first), int(second)):
            return "/"

        return "+"

    def get_placing_display(self, user, category: int, stat: int):
        placing = self.ctx.bot.lbs[category].stats[stat].get_placing(user.id)

        if placing is None:
            return f"(> {LB_LENGTH})", False

        placing = placing[0]

        if placing == 1:
            emoji = ":first_place:"

        elif placing == 2:
            emoji = ":second_place:"

        elif placing == 3:
            emoji = ":third_place:"

        else:
            return f"({humanize.ordinal(placing)})", False

        return emoji, True

    def get_thin_spacing(self, text: str, is_emoji: bool):
        if is_emoji:
            s = 9
        else:
            s = 0

            for c in text:
                if c == ",":
                    s += 1.5
                elif c in ["1", "(", ")"]:
                    s += 2
                elif c == "h":
                    s += 3
                else:
                    s += 4

        return math.ceil(s)

    def format_account_stat(self, num: str, intended: int):
        num_spacing = intended - self.get_thin_spacing(num, False)

        return f"{num}{num_spacing * THIN_SPACE}"

    def create_account_page(self, embed):
        embed.set_thumbnail(url="https://i.imgur.com/KrXiy9S.png")

        in_between = 35
        b = in_between * THIN_SPACE

        embed.title += f"\n\nAlltime{b}Season{b}24h{b}** **"

        fr_words = self.format_account_stat(f"{self.user.words:,}", 6 + in_between)
        fr_xp = self.format_account_stat(f"{self.user.xp:,}", 17 + in_between)
        fr_24_words = f"{sum(self.user.last24[0]):,}"

        if self.user.badges == []:
            badges = "User has no badges..."
        else:
            badges = " ".join(self.user.badge_emojis)

        embed.description = (
            f"**Words:** {fr_words}**XP:** {fr_xp}**XP:** {fr_24_words}\n\n"
            f"**Badges ({len(self.user.badges)})**\n"
            f"{badges}"
        )

        embed.add_field(
            name=f"Trophies ({sum(self.user.trophies)})",
            value=f"{THIN_SPACE*6}".join(
                f"{icons.trophies[i]} x{t}" for i, t in enumerate(self.user.trophies)
            ),
            inline=False,
        )

        s = THIN_SPACE * 3

        embed.add_field(
            name="** **",
            value=f"**{LINE_SPACE * 9}{s}Information{s}{LINE_SPACE * 9}**",
            inline=False,
        )

        embed.add_field(name="Created", value=f"<t:{self.user.unix_created_at}:R>")

        embed.add_field(name="Votes", value=self.user.votes)

        embed.add_field(
            name="Daily Streak",
            value=f"{self.user.streak} ({self.user.highest_streak})",
        )

        embed.add_field(
            name=f"{LINE_SPACE * 9}{s}Settings{s}{LINE_SPACE * 10}",
            value="** **",
            inline=False,
        )

        theme_name, theme_icon = get_theme_display(self.user.theme)

        pacer_display = get_pacer_display(self.user.pacer_type, self.user.pacer_speed)

        embed.add_field(name="Theme", value=f"{theme_icon} {theme_name}")

        embed.add_field(
            name="Language",
            value=f"{self.user.language.capitalize()} ({self.user.level.capitalize()})",
        )

        embed.add_field(
            name="Pacer",
            value=pacer_display,
        )

        return embed

    def create_typing_page(self, embed):
        embed.title += f"{THIN_SPACE*115}** **"
        embed.set_thumbnail(url="https://i.imgur.com/BZzMGjc.png")
        embed.add_field(
            name="High Scores",
            value="Scores are divided by word count range",
            inline=False,
        )

        hs1, hs2, hs3 = self.user.highspeed.values()

        # Short high score
        placing = self.get_placing_display(self.user, 3, 0)[0]

        embed.add_field(
            name=f"Range:{THIN_SPACE*26}10-20:",
            value=(
                f"Wpm:{THIN_SPACE*28}{hs1.wpm}\n"
                f"Accuracy:{THIN_SPACE*17}{hs1.acc}%\n"
                f"Placing:{THIN_SPACE*23}**{placing}**"
            ),
        )

        # Medium high score
        placing = self.get_placing_display(self.user, 3, 1)[0]

        embed.add_field(
            name="21-50:",
            value=(f"{hs2.wpm}\n{hs2.acc}%\n**{placing}**"),
        )

        placing = self.get_placing_display(self.user, 3, 2)[0]

        embed.add_field(
            name="51-100:",
            value=(f"{hs3.wpm}\n{hs3.acc}%\n**{placing}**"),
        )

        wpm, raw, acc, cw, tw, scores = get_typing_average(self.user)

        con = calculate_score_consistency(scores)

        # Average

        wpm_perc = self.get_perc_sign(wpm * len(scores), self.ctx.bot.avg_perc[0])
        raw_perc = self.get_perc_sign(raw * len(scores), self.ctx.bot.avg_perc[1])
        acc_perc = self.get_perc_sign(acc * len(scores), self.ctx.bot.avg_perc[2])

        # Consistency percentile is based on arbitrary values
        con_perc = "+" if con >= 70 else "/" if con >= 40 else "-"

        embed.add_field(
            name="Average (Last 10 Tests)",
            value=(
                "```diff\n"
                f"{wpm_perc} Wpm: {wpm}\n"
                f"{raw_perc} Raw Wpm: {raw}\n"
                f"{acc_perc} Accuracy: {acc}% ({cw} / {tw})\n"
                f"{con_perc} Consistency: {con}%```"
            ),
        )

        embed.add_field(name="Recent Typing Scores", value="** **", inline=False)

        url = get_graph_link(user=self.user, amt=10, dimensions=(8, 4))

        embed.set_image(url=url)

        return embed

    def get_embed_callbacks(self):
        return {
            "Account": ["\N{BAR CHART}", self.create_account_page],
            "Typing": ["\N{KEYBOARD}", self.create_typing_page],
        }

    async def start(self):
        embed = self.get_embed()

        selector = ProfileSelect(self.callbacks)

        self.add_item(item=selector)

        await self.ctx.respond(embed=embed, view=self)


class ProfileSelect(discord.ui.Select):
    def __init__(self, callbacks):

        self.callbacks = callbacks

        super().__init__(
            placeholder="Select a category...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=name, emoji=value[0])
                for name, value in self.callbacks.items()
            ],
        )

    async def callback(self, interaction):
        option = self.values[0]

        if option != self.view.page:

            self.view.page = option

            await self.view.update_message(interaction)


class AchievementsButton(DictButton):
    def __init__(self, user, **kwargs):
        super().__init__(**kwargs)

        self.style = (
            discord.ButtonStyle.success
            if categories[self.label].is_done(user)
            else discord.ButtonStyle.danger
        )

    @property
    def is_display_success(self):
        return self.disabled

    def toggle_success(self):
        self.disabled = True

    def toggle_regular(self):
        self.disabled = False


class AchievementsView(ViewFromDict):
    def __init__(self, ctx, user):
        super().__init__(ctx, categories)

        self.user = user  # user data

    def button(self, **kwargs):
        return AchievementsButton(self.user, **kwargs)

    async def create_page(self):
        c = self.the_dict[self.page]

        embed = self.ctx.embed(
            title=f"{self.user.display_name} | {self.page}",
            description=c.desc
            + (
                f"\n\n**Completion Reward:** {c.reward.desc}"
                if c.reward is not None
                else ""
            ),
        )

        for a in c.challenges:
            a, emoji, display, bar_display = await get_achievement_display(
                self.ctx, self.user, a
            )

            embed.add_field(
                name=f"**{emoji} {a.name}{display}**",
                value=f">>> {a.desc}\n{bar_display}",
                inline=False,
            )

        return embed


class Bot(commands.Cog):
    """Core bot commands"""

    emoji = "\N{ROBOT FACE}"
    order = 1

    def __init__(self, bot):
        self.bot = bot

    @cooldown(7, 2)
    @bridge.bridge_command()
    @user_option
    async def profile(self, ctx, user: discord.User = None):
        """View user statistics"""
        await self.handle_profile_cmd(ctx, user)

    @cooldown(7, 2)
    @commands.user_command(name="Typing Profile")
    async def profile_user(self, ctx, member: discord.Member):
        await self.handle_profile_cmd(ctx, member)

    async def handle_profile_cmd(self, ctx, user):
        user = await user_check(ctx, user)

        view = ProfileView(ctx, user)

        await view.start()

    @cooldown(5, 2)
    @bridge.bridge_command()
    @user_option
    async def graph(self, ctx, user: discord.User = None):
        """See a graph of a user's typing scores"""
        await self.handle_graph_cmd(ctx, user)

    @cooldown(5, 2)
    @commands.user_command(name="Typing Graph")
    async def graph_user(self, ctx, member: discord.Member):
        await self.handle_graph_cmd(ctx, member)

    async def handle_graph_cmd(self, ctx, user):
        user_data = await self.handle_scores(ctx, user)

        if user_data is None:
            return

        view = GraphView(ctx, user_data)
        await view.start()

    @cooldown(6, 2)
    @bridge.bridge_command()
    async def leaderboard(self, ctx):
        """See the top users in any category"""

        view = LeaderboardView(ctx, ctx.initial_user)

        await view.start()

    @cooldown(5, 2)
    @bridge.bridge_command()
    @user_option
    async def achievements(self, ctx, user: discord.User = None):
        """See all the achievements"""
        user_data = await user_check(ctx, user)

        view = AchievementsView(ctx, user_data)

        await view.start()

    @cooldown(5, 2)
    @bridge.bridge_command()
    async def challenges(self, ctx):
        """View the daily challenges and your progress on them"""

        user = ctx.initial_user

        challenges, reward = get_daily_challenges()

        # Getting the unix time of tomorrow
        today = datetime.utcnow()

        end_of_today = datetime(
            year=today.year,
            month=today.month,
            day=today.day,
            hour=23,
            minute=59,
            second=59,
            tzinfo=timezone.utc,
        )

        unix_timestamp = int(end_of_today.timestamp())

        embed = ctx.embed(
            title="Daily Challenges",
            description=(
                f"**Today's daily challenge restarts in** <t:{unix_timestamp}:R>\n\n"
                "Complete all the daily challenges to earn:\n"
                f"**{reward.desc}**"
            ),
        )

        content = ""

        for i, c in enumerate(challenges):
            # Getting the user's progress on the challenge
            p = await c.progress(ctx, user)

            # Generating the progress bar
            bar = get_bar(p[0] / p[1])

            emoji = icons.success if user.daily_completion[i] else icons.danger

            content += (
                f"**{emoji} Challenge {i+1}**\n"
                f"> {c.desc}\n"
                f"> {bar} `{p[0]}/{p[1]}`\n\n"
            )

        embed.add_field(
            name="** **",
            value=content,
            inline=False,
        )

        await ctx.respond(embed=embed)

        await ctx.respond(
            "Challenges restart at the same time every day!", ephemeral=True
        )

    @cooldown(6, 2)
    @bridge.bridge_command()
    async def season(self, ctx):
        """Information about the monthly season and your progress in it"""
        view = SeasonView(ctx)
        await view.start()

    async def handle_scores(self, ctx, user):
        user_data = await user_check(ctx, user)

        if len(user_data.scores) == 0:
            embed = ctx.error_embed(
                title=f"{icons.caution} User does not have any scores saved:",
                description="> Please complete at least 1 typing test or race using `/tt`",
            )
            await ctx.respond(embed=embed)
            return

        return user_data

    @cooldown(6, 2)
    @bridge.bridge_command()
    @user_option
    async def scores(self, ctx, user: discord.User = None):
        """View and download a user's recent typing scores"""
        user_data = await self.handle_scores(ctx, user)

        if user_data is None:
            return

        view = ScoreView(ctx, user_data)

        await view.start()

    @cooldown(5, 2)
    @bridge.bridge_command()
    @user_option
    async def badges(self, ctx, user: discord.User = None):
        """View a user's badges"""
        user_data = await user_check(ctx, user)

        if len(user_data.badges) == 0:
            embed = ctx.error_embed(
                title=f"{icons.caution} User does not have any badges"
            )

        else:
            badges = " ".join(user_data.badge_emojis)

            embed = ctx.embed(
                title=f"{user_data.display_name} | Badges", description=badges
            )

        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(Bot(bot))
