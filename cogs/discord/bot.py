import csv
import json
import math
import time
import zlib
from datetime import datetime, timezone
from io import BytesIO, StringIO
from typing import TYPE_CHECKING

import discord
import humanize
from cryptography.fernet import Fernet
from discord.ext import bridge, commands

import data.icons as icons
from bot import Context, WordPractice
from challenges.achievements import (
    categories,
    get_achievement_display,
    is_category_complete,
)
from challenges.daily import get_daily_challenges
from challenges.season import get_season_tiers
from config import GRAPH_CDN_SECRET
from data.constants import (
    AVG_AMT,
    GRAPH_CDN_BASE_URL,
    GRAPH_EXPIRE_TIME,
    LB_DISPLAY_AMT,
    LB_LENGTH,
    PREMIUM_LINK,
    REGULAR_SCORE_LIMIT,
    SCORE_SAVE_AMT,
)
from helpers.checks import cooldown, user_check
from helpers.converters import user_option
from helpers.ui import BaseView, DictButton, ScrollView, ViewFromDict
from helpers.user import get_pacer_display, get_theme_display, get_typing_average
from helpers.utils import (
    calculate_score_consistency,
    cmd_run_before,
    get_bar,
    get_lb_display,
    get_users_from_lb,
)

if TYPE_CHECKING:
    from cogs.utils.mongo import User

# Spacing characters
THIN_SPACE = "\N{THIN SPACE}"

LINE_SPACE = "\N{BOX DRAWINGS LIGHT HORIZONTAL}"

# Season command
EMOJIS_PER_TIER = 4
SEASON_TROPHY_DATA = [
    ["Gold Trophy", icons.trophies[0], [1, 1]],
    ["Silver Trophy", icons.trophies[1], [2, 2]],
    ["Bronze Trophy", icons.trophies[2], [3, 3]],
    ["Top 10 Trophy", icons.trophies[3], [4, 10]],
]


async def _get_lb_placing(lb_data, c, user_id):
    if user_id in lb_data:
        placing = list(lb_data.keys()).index(user_id) + 1
    else:
        placing = None

    lb_placing = placing

    if placing is None:
        placing = await c.get_placing(user_id)

    return placing, lb_placing


def get_graph_link(*, user, amt: int, dimensions: tuple):
    values = [[], [], []]

    round_amt = 2 if amt <= 25 else 1 if amt <= 50 else 0

    round_num = lambda n: int(b) if (b := round(n, round_amt)).is_integer() else b

    for s in user.scores[-amt:]:
        values[0].append(round_num(s.wpm))
        values[1].append(round_num(s.raw))
        values[2].append(round_num(s.acc))

    labels = ["Wpm", "Raw Wpm", "Accuracy"]

    y_values = dict(zip(labels, values))

    payload = {
        "fig_size": dimensions,
        "until": int(time.time() + GRAPH_EXPIRE_TIME),
        "y_values": y_values,
        "colours": user.theme + ["#ffffff"],
    }

    # Encrypting the data
    encoded_data = zlib.compress(json.dumps(payload, separators=(",", ":")).encode())

    encrypted_data = Fernet(GRAPH_CDN_SECRET.encode()).encrypt(encoded_data)

    data = encrypted_data.decode()

    return f"{GRAPH_CDN_BASE_URL}/score_graph?raw_data={data}"


class SeasonView(ViewFromDict):
    def __init__(self, ctx: Context):
        categories = {
            "Trophies": self.get_season_trophy,
            "Rewards": self.get_reward_embed,
            "Information": self.get_info_embed,
        }

        super().__init__(ctx, categories)

        self.season_info = None

    async def get_info_embed(self):
        embed = self.ctx.embed(title=f"Season Information")

        leaderboard_info = (
            f"The season leaderboard can be viewed with `{self.ctx.prefix}leaderboard`"
        )

        if self.season_info["enabled"] is False:
            leaderboard_info += " under the season category"

        leaderboard_info += "."

        info = {
            "What are seasons?": "Seasons are a month-long competition where users compete to earn the most XP.",
            "How do I earn XP?": f"XP {icons.xp} can be earned by completing typing tests, daily challenges, voting and more.",
            "What are trophies?": "Trophies are awarded to the top 10 users at the end of the season. Current trophy distribution can be found by clicking the `Trophies` button below.",
            "What are season rewards?": "By earning XP, users can win exclusive badges. View your progress by clicking the `Rewards` button below.",
            "How do I view the season leaderboads?": leaderboard_info,
        }

        for i, (title, desc) in enumerate(info.items()):
            spacing = "** **\n" if i != 0 else ""

            embed.add_field(name=f"{spacing}{title}", value=desc, inline=False)

        embed.set_thumbnail(url="https://i.imgur.com/0Mzb6Js.png")

        return embed

    async def get_reward_embed(self):
        embed = self.ctx.embed(
            title=f"Season {self.season_info['number']} Rewards",
            description=(
                "Unlock seasonal badges as you earn XP\n\n"
                f"{icons.xp} **{self.user.xp:,} XP**\n\n"
            ),
        )

        embed.set_thumbnail(url="https://i.imgur.com/sQQXQsw.png")

        challenges = [v async for v in get_season_tiers(self.ctx.bot)]

        if self.season_info["enabled"] is False:
            embed.description = "Sorry, there is no season right now..."

        elif challenges == []:
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

    async def get_season_trophy(self):
        embed = self.ctx.embed(
            title=f"Season {self.season_info['number']} Trophy Distribution",
            description=(
                f"Earn trophies to display on your account by placing\n"
                "in the montly season.\n\n"
                f"View the full leaderboard with `{self.ctx.prefix}leaderboard`"
            ),
        )

        embed.set_thumbnail(url="https://i.imgur.com/OvcJTuI.png")

        if self.season_info["enabled"] is False:
            embed.description = "Sorry, there is no season right now..."

        else:
            for name, icon, (start, end) in SEASON_TROPHY_DATA:
                lb_placings = []

                for i in range(start - 1, end):
                    if i >= len(self.lb_data):
                        break

                    u, value = self.lb_data[i]

                    lb_display = get_lb_display(
                        i + 1, self.category.unit, u, value, self.ctx.author.id
                    )

                    lb_placings.append(lb_display)

                if lb_placings != []:
                    embed.add_field(
                        name=f"{name} {icon}",
                        value="\n".join(lb_placings),
                        inline=False,
                    )

            if self.lb_placing is None:
                placing = "N/A" if self.placing is None else self.placing

                value = self.category.get_stat(self.user)

                display = get_lb_display(placing, self.category.unit, self.user, value)

                embed.add_field(
                    name=f"{LINE_SPACE * 13}\n{display}",
                    value="** **",
                    inline=False,
                )

        return embed

    async def create_page(self):
        return await self.the_dict[self.page]()

    @property
    def category(self):
        return self.ctx.bot.lbs[1].stats[0]

    @property
    def user(self):
        return self.ctx.initial_user

    async def start(self):
        self.season_info = await self.ctx.bot.mongo.get_season_info()

        # Getting the highest placing that will be displayed
        end = SEASON_TROPHY_DATA[-1][2][1]

        raw_lb_data = await self.category.get_lb_data(end)

        self.lb_data = await get_users_from_lb(self.ctx.bot, raw_lb_data)

        # Getting the placing of the author
        self.placing, self.lb_placing = await _get_lb_placing(
            raw_lb_data, self.category, self.ctx.author.id
        )

        return await super().start()


class GraphButton(DictButton):
    def __init__(self, is_premium, **kwargs):
        self.is_premium = is_premium

        super().__init__(**kwargs)

    def toggle_eligible(self, value):
        if self.is_premium is False and value >= REGULAR_SCORE_LIMIT:
            self.disabled = True


class GraphView(ViewFromDict):
    def __init__(self, ctx: Context, user):
        test_amts = [10, 25, 50, 100, 200]

        super().__init__(ctx, {f"{i} Tests": i for i in test_amts})

        self.user = user

        self.link_cache = {}  # amt: link

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
                f"**Wpm:** {wpm}\n" f"**Raw:** {raw}\n" f"**Acc:** {acc}% ({cw} / {tw})"
            ),
            inline=True,
        )

        embed.add_field(name="`Best`", value=f"**Wpm:** {highest.wpm}", inline=True)

        embed.add_field(name="`Lowest`", value=f"**Wpm:** {lowest.wpm}", inline=True)

        total = len(scores)

        if total in self.link_cache:
            url = self.link_cache[total]

        else:
            url = get_graph_link(
                user=self.user,
                amt=amt,
                dimensions=(6, 4),
            )

            self.link_cache[total] = url

        if self.user.is_premium is False:
            embed.set_footer(
                text=f"Premium Members can save up to {SCORE_SAVE_AMT} tests"
            )

        embed.set_image(url=url)

        return embed


class ScoreView(ScrollView):
    def __init__(self, ctx: Context, user):
        self.user = user

        iter = self.get_user_scores()

        super().__init__(ctx, iter=iter, per_page=3)

    def get_user_scores(self):
        limit = SCORE_SAVE_AMT if self.user.is_premium else REGULAR_SCORE_LIMIT

        return self.user.scores[::-1][:limit]

    def get_formatted_data(self):
        data_labels = {
            "Wpm": "wpm",
            "Raw Wpm": "raw",
            "Accuracy": "acc",
            "Correct Words": "cw",
            "Total Words": "tw",
            "Experience": "xp",
            "Unix Timestamp": "unix_timestamp",
        }

        data = {n: [] for n in data_labels.keys()}

        for s in self.iter:
            for n, v in data_labels.items():
                data[n].append(getattr(s, v))

        return data

    async def send_as_file(self, buffer, ext, button, interaction):
        file = discord.File(fp=buffer, filename=f"scores.{ext}")

        await interaction.response.send_message(file=file)

        button.disabled = True

        await interaction.message.edit(view=self)

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
        embed = self.ctx.embed(
            title=f"{self.user.display_name} | Recent Scores ({self.start_page + 1} - {self.end_page} of {self.total})",
            description=" "
            if self.user.is_premium
            else f"**[Premium Members]({PREMIUM_LINK})** can download and save up to {SCORE_SAVE_AMT} test scores!",
        )

        for i, s in enumerate(self.items):
            timestamp = s.unix_timestamp

            embed.add_field(
                name=f"Score {self.start_page + i + 1} ({s.test_type})",
                value=(
                    f">>> **Wpm:** {s.wpm}\n"
                    f"**Raw:** {s.raw}\n"
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
    def __init__(self, lbs):
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
                for i, lb in enumerate(lbs)
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
    def __init__(self, ctx: Context):
        super().__init__(ctx, iter=self.get_iter, per_page=10, row=2)

        self.timeout = 60

        # Caches the data for each leaderboard {lb_key: (lb, placing, lb_placing)}
        self.lb_data = {}

        self.active_btns = []

    def get_iter(self):
        lb = self.lb_data.get(self.c.lb_key)

        if lb is None:
            return None

        return lb[0]

    @property
    def total(self):
        return LB_DISPLAY_AMT

    @property
    def user(self):
        return self.ctx.initial_user

    @property
    def lb(self):
        return self.lbs[self.category]

    @property
    def c(self):
        return self.lb.stats[self.stat]

    async def create_page(self):
        embed = self.ctx.embed(
            title=f"{self.lb.title} Leaderboard | Page {self.page + 1}"
        )

        # Checking if the leaderboard data was cached
        if self.c.lb_key in self.lb_data:
            lb, placing, _ = self.lb_data[self.c.lb_key]

        else:
            raw_lb_data = await self.c.get_lb_data()

            lb = await get_users_from_lb(self.ctx.bot, raw_lb_data)

            placing, lb_placing = await _get_lb_placing(
                raw_lb_data, self.c, self.ctx.author.id
            )

            self.lb_data[self.c.lb_key] = (lb, placing, lb_placing)

        # Generating the leaderboard UI
        for i, (u, value) in enumerate(self.items):
            p = self.start_page + i + 1

            lb_display = get_lb_display(p, self.c.unit, u, value, self.ctx.author.id)

            embed.add_field(
                name=lb_display,
                value="** **",
                inline=False,
            )

        place_display = "N/A" if placing is None else placing

        count = self.c.get_stat(self.user)

        display = get_lb_display(place_display, self.c.unit, self.user, count)

        embed.add_field(
            name=f"{LINE_SPACE * 13}\n{display}",
            value="** **",
            inline=False,
        )

        return embed

    async def jump_to_placing(self, interaction):
        # The leaderboard data has to be cached for the user to be on the page
        lb_placing = self.lb_data[self.c.lb_key][2]

        if lb_placing is None:
            return await interaction.response.send_message(
                f"You are outside of the top {self.total}", ephemeral=True
            )

        # Getting the page where the user is placed
        page = int((lb_placing - 1) / 10)

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

        # Getting all the elligible leaderboards
        self.lbs = [lb for lb in self.ctx.bot.lbs if await lb.check(self.ctx)]

        # Getting the starting category based on priority
        self.category, _ = max(enumerate(self.lbs), key=lambda x: x[1].priority)

        self.stat = self.lb.default

        select = LeaderboardSelect(self.lbs)
        self.add_item(select)

        await super().start()


class ProfileView(BaseView):
    def __init__(self, ctx: Context, user: "User"):
        super().__init__(ctx)

        self.user = user
        self.callbacks = self.get_embed_callbacks()
        self.page = list(self.callbacks.keys())[0]

    async def update_message(self, interaction):
        embed = await self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    async def get_embed(self):
        """Generates the base embed for all the pages"""
        base_embed = self.get_base_embed(self.page)

        return await self.callbacks[self.page][1](base_embed)

    def get_base_embed(self, page_name):
        embed = self.ctx.embed(title=self.user.display_name)
        embed.set_author(
            name=f"{self.user.username} | {page_name}",
            icon_url=self.user.avatar_url,
        )
        return embed

    def get_perc_sign(self, value: int, percs: tuple[int, int]):
        first, second = percs

        if value < int(first):
            return "-"

        if value < int(second):
            return "/"

        return "+"

    async def get_placing_display(self, user, category: int, stat: int):
        c = self.ctx.bot.lbs[category].stats[stat]

        placing = await c.get_placing(user.id)

        if placing is None:
            return f"(> {LB_LENGTH})"

        placing += 1

        if placing == 1:
            emoji = ":first_place:"

        elif placing == 2:
            emoji = ":second_place:"

        elif placing == 3:
            emoji = ":third_place:"

        else:
            return f"({humanize.ordinal(placing)})"

        return emoji

    def get_thin_spacing(self, text: str, is_emoji: bool):
        if is_emoji:
            return 9

        s = 0

        for c in text:
            if c == ",":
                s += 1.35
            elif c == "0":
                s += 3.1
            elif c == "1":
                s += 2
            elif c in ["2", "5", "9"]:
                s += 2.75
            elif c in ["3", "4", "6"]:
                s += 2.85
            elif c == "7":
                s += 2.25
            else:
                s += 2.85

        return math.ceil(s)

    def format_account_stat(self, num: str, intended: int):
        num_spacing = intended - self.get_thin_spacing(num, False)

        return f"{num}{num_spacing * THIN_SPACE}"

    async def create_account_page(self, embed):
        embed.set_thumbnail(url="https://i.imgur.com/KrXiy9S.png")

        in_between = 23
        b = in_between * THIN_SPACE

        embed.title += f"\n\nAll Time{b}Season{b}24h{b}** **"

        fr_words = self.format_account_stat(f"{self.user.words:,}", 9 + in_between)
        fr_xp = self.format_account_stat(f"{self.user.xp:,}", 13 + in_between)
        fr_24_xp = f"{sum(self.user.xp_24h):,}"

        if self.user.badges == []:
            badges = "User has no badges..."
        else:
            badges = " ".join(b.raw for b in self.user.badge_objs)

        embed.description = (
            f"**Words:** {fr_words}**XP:** {fr_xp}**XP:** {fr_24_xp}\n\n"
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
            value=f"**{LINE_SPACE * 18}{s}Information{s}{LINE_SPACE * 16}**",
            inline=False,
        )

        embed.add_field(name="Created", value=f"<t:{self.user.unix_created_at}:R>")

        embed.add_field(name="Votes", value=self.user.votes)

        embed.add_field(
            name="Daily Streak",
            value=f"{self.user.streak} ({self.user.highest_streak})",
        )

        embed.add_field(
            name=f"{LINE_SPACE * 18}{s}Settings{s}{LINE_SPACE * 19}",
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

    async def create_typing_page(self, embed):
        embed.set_thumbnail(url="https://i.imgur.com/BZzMGjc.png")
        embed.add_field(
            name="High Scores",
            value="Scores are divided by word count range",
            inline=False,
        )

        hs1, hs2, hs3 = self.user.highspeed.values()

        # Short high score
        placing = await self.get_placing_display(self.user, 3, 0)

        embed.add_field(
            name=f"Range:{THIN_SPACE*23}10-20:",
            value=(
                f"Wpm:{THIN_SPACE*26}{hs1.wpm}\n"
                f"Accuracy:{THIN_SPACE*15}{hs1.acc}%\n"
                f"Placing:{THIN_SPACE*19}**{placing}**"
            ),
        )

        # Medium high score
        placing = await self.get_placing_display(self.user, 3, 1)

        embed.add_field(
            name="21-50:",
            value=(f"{hs2.wpm}\n{hs2.acc}%\n**{placing}**"),
        )

        placing = await self.get_placing_display(self.user, 3, 2)

        embed.add_field(
            name="51-100:",
            value=(f"{hs3.wpm}\n{hs3.acc}%\n**{placing}**"),
        )

        wpm, raw, acc, cw, tw, scores = get_typing_average(self.user)

        con = calculate_score_consistency(scores)

        # Average

        wpm_perc = self.get_perc_sign(wpm, self.ctx.bot.avg_perc[0])
        raw_perc = self.get_perc_sign(raw, self.ctx.bot.avg_perc[1])
        acc_perc = self.get_perc_sign(acc, self.ctx.bot.avg_perc[2])

        # Consistency percentile is based on arbitrary values
        con_perc = "+" if con >= 70 else "/" if con >= 40 else "-"

        embed.add_field(
            name=f"Average (Last {AVG_AMT} Tests)",
            value=(
                "```diff\n"
                f"{wpm_perc} Wpm: {wpm}\n"
                f"{raw_perc} Raw Wpm: {raw}\n"
                f"{acc_perc} Accuracy: {acc}% ({cw} / {tw})\n"
                f"{con_perc} Consistency: {con}%```"
            ),
        )

        embed.add_field(name="Last 10 Typing Scores", value="** **", inline=False)

        url = get_graph_link(user=self.user, amt=10, dimensions=(8, 4))

        embed.set_image(url=url)

        return embed

    def get_embed_callbacks(self):
        return {
            "Account": ["\N{BAR CHART}", self.create_account_page],
            "Typing": ["\N{KEYBOARD}", self.create_typing_page],
        }

    async def start(self):
        embed = await self.get_embed()

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
            if is_category_complete(categories[self.label], user)
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
    def __init__(self, ctx: Context, user):
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
            add_footer=False,
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

        embed.set_footer(text="An orange bar indicates a bonus achievement")

        return embed


class Bot(commands.Cog):
    """Core bot commands"""

    emoji = "\N{ROBOT FACE}"
    order = 1

    def __init__(self, bot: WordPractice):
        self.bot = bot

    @bridge.bridge_command()
    @cooldown(7, 2)
    @user_option
    async def profile(self, ctx: Context, *, user: discord.User = None):
        """View user statistics"""
        await self.handle_profile_cmd(ctx, user)

    @commands.user_command(name="Typing Profile")
    @cooldown(7, 2)
    async def profile_user(self, ctx: Context, member: discord.Member):
        await self.handle_profile_cmd(ctx, member)

    async def handle_profile_cmd(self, ctx: Context, user):
        user = await user_check(ctx, user)

        view = ProfileView(ctx, user)

        await view.start()

    @bridge.bridge_command()
    @cooldown(5, 2)
    @user_option
    async def graph(self, ctx: Context, *, user: discord.User = None):
        """See a graph of a user's typing scores"""
        await self.handle_graph_cmd(ctx, user)

    @commands.user_command(name="Typing Graph")
    @cooldown(5, 2)
    async def graph_user(self, ctx: Context, member: discord.Member):
        await self.handle_graph_cmd(ctx, member)

    async def handle_graph_cmd(self, ctx: Context, user):
        user_data = await self.handle_scores(ctx, user)

        if user_data is None:
            return

        view = GraphView(ctx, user_data)
        await view.start()

    @bridge.bridge_command()
    @cooldown(10, 5)
    async def leaderboard(self, ctx: Context):
        """See the top users in any category"""

        await ctx.defer()

        view = LeaderboardView(ctx)

        await view.start()

    @bridge.bridge_command()
    @cooldown(5, 2)
    @user_option
    async def achievements(self, ctx: Context, *, user: discord.User = None):
        """See all the achievements"""
        user_data = await user_check(ctx, user)

        view = AchievementsView(ctx, user_data)

        await view.start()

    @bridge.bridge_command()
    @cooldown(5, 2)
    async def challenges(self, ctx: Context):
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
                f"**Today's daily challenge restarts ** <t:{unix_timestamp}:R>\n\n"
                "Complete all the daily challenges to earn:\n"
                f"**{reward.desc}**"
            ),
        )

        content = ""

        for i, c in enumerate(challenges):
            is_complete = user.daily_completion[i]

            # Getting the user's progress on the challenge
            p1, p2 = await c.progress(ctx, user)

            if is_complete:
                p1 = max(p1, p2)

            # Generating the progress bar
            bar = get_bar(p1 / p2)

            emoji = icons.success if is_complete else icons.danger

            content += (
                f"**{emoji} Challenge {i+1}**\n"
                f"> {c.desc}\n"
                f"> {bar} `{p1}/{p2}`\n\n"
            )

        embed.add_field(
            name="** **",
            value=content,
            inline=False,
        )

        await ctx.respond(embed=embed)

        if not cmd_run_before(ctx, user):
            await ctx.respond(
                "Challenges restart at the same time every day!", ephemeral=True
            )

    @bridge.bridge_command()
    @cooldown(6, 2)
    async def season(self, ctx: Context):
        """Information about the monthly season and your progress in it"""
        view = SeasonView(ctx)
        await view.start()

    async def handle_scores(self, ctx: Context, user):
        user_data = await user_check(ctx, user)

        if len(user_data.scores) == 0:
            embed = ctx.error_embed(
                title=f"{icons.caution} User does not have any scores saved:",
                description="> Please complete at least 1 typing test or race using `/tt`",
            )
            await ctx.respond(embed=embed)
            return

        return user_data

    @bridge.bridge_command()
    @cooldown(6, 2)
    @user_option
    async def scores(self, ctx: Context, *, user: discord.User = None):
        """View and download a user's recent typing scores"""
        user_data = await self.handle_scores(ctx, user)

        if user_data is None:
            return

        view = ScoreView(ctx, user_data)

        await view.start()

    @bridge.bridge_command()
    @cooldown(5, 2)
    @user_option
    async def badges(self, ctx: Context, *, user: discord.User = None):
        """View a user's badges"""
        user_data = await user_check(ctx, user)

        if len(user_data.badges) == 0:
            embed = ctx.error_embed(
                title=f"{icons.caution} User does not have any badges"
            )

        else:
            badges = " ".join(b.raw for b in user_data.badge_objs)

            embed = ctx.embed(
                title=f"{user_data.display_name} | Badges", description=badges
            )

        await ctx.respond(embed=embed)


def setup(bot: WordPractice):
    bot.add_cog(Bot(bot))
