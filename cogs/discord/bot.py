import csv
import json
import math
from datetime import datetime, timezone
from io import BytesIO, StringIO

import discord
import humanize
from discord.ext import commands

import icons
from achievements import categories, get_achievement_tier, get_bar
from achievements.challenges import get_daily_challenges
from achievements.season import get_season_tiers
from constants import COMPILE_INTERVAL, LB_DISPLAY_AMT, LB_LENGTH, PREMIUM_LINK
from helpers.checks import cooldown, user_check
from helpers.converters import opt_user
from helpers.ui import BaseView, DictButton, ScrollView, ViewFromDict
from helpers.user import get_pacer_display, get_theme_display, get_typing_average
from helpers.utils import calculate_score_consistency, cmd_run_before

TS = "\N{THIN SPACE}"
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


class SeasonView(ViewFromDict):
    def __init__(self, ctx, user):
        categories = {
            "Information": self.get_info_embed,
            "Rewards": self.get_reward_embed,
        }

        super().__init__(ctx, categories)

        self.user = user

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

        p = self.user.xp / challenges[-1][0]

        bar = get_bar(
            p, size=EMOJIS_PER_TIER * len(challenges), vertical=True, split=True
        )

        for i, (amt, r) in enumerate(challenges):
            emoji = icons.green_dot if self.user.xp >= amt else icons.red_dot

            index = (i + 1) * EMOJIS_PER_TIER - 1

            bar[index] += f"{emoji}**{r.badge_format()}** *{amt/1000:g}k*"

        embed.description += "\n".join(bar)

        return embed

    async def create_page(self):
        return await self.the_dict[self.page]()


class GraphView(ViewFromDict):
    def __init__(self, ctx, user):
        test_amts = [10, 25, 50, 100]

        super().__init__(ctx, {f"{i} Tests": i for i in test_amts})

        self.user = user

    @property
    def user_scores(self):
        return self.user.scores[::-1][: self.the_dict[self.page]]

    async def create_page(self):

        embed = self.ctx.embed(
            title="Graph",
        )

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
            else f"**[Patrons]({PREMIUM_LINK})** can download test scores",
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

            username = f"{u['name']}#{u['discriminator']} {u['status']}"

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
        page = int((self.placing - 1) / 10)

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
        await interaction.message.edit(embed=embed, view=self)

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

    def create_achievements_page(self, embed):
        embed.set_thumbnail(url="https://i.imgur.com/sQQXQsw.png")

        return embed

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

        return f"{num}{num_spacing * TS}"

    def create_account_page(self, embed):
        embed.set_thumbnail(url="https://i.imgur.com/KrXiy9S.png")

        in_between = 35
        b = in_between * TS

        # TODO: add placings
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
            value=f"{TS*6}".join(
                f"{icons.trophies[i]} x{t}" for i, t in enumerate(self.user.trophies)
            ),
            inline=False,
        )

        s = TS * 3

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
        embed.title += f"{TS*115}** **"
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
            name=f"Range:{TS*26}10-20:",
            value=(
                f"Wpm:{TS*28}{hs1.wpm}\n"
                f"Accuracy:{TS*17}{hs1.acc}%\n"
                f"Placing:{TS*23}**{placing}**"
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

        return embed

    def create_ranking_page(self, embed):
        return embed

    def get_embed_callbacks(self):
        return {
            "Account": ["\N{BAR CHART}", self.create_account_page],
            "Typing": ["\N{KEYBOARD}", self.create_typing_page],
            "Achievements": ["\N{SHIELD}", self.create_achievements_page],
            "Rankings": ["\N{TROPHY}", self.create_ranking_page],
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

        embed = self.ctx.embed(title=f"{self.page}", description=c.desc)

        for a in c.challenges:
            tier_display = ""

            # Tiers
            if isinstance(a, list):
                all_names = [m.name for m in a]

                names = set(all_names)

                tier = get_achievement_tier(self.user, len(all_names), names)

                a = a[tier]

                tier_display = f" `[{tier + 1}/{len(all_names)}]`"

            p = await a.progress(self.ctx, self.user)

            bar = get_bar(p[0] / p[1])

            emoji = (
                icons.success
                if await a.is_completed(self.ctx, self.user)
                else icons.danger
            )

            reward_display = (
                f"**Reward:** {a.reward.desc}\n" if a.reward is not None else ""
            )

            embed.add_field(
                name=f"**{emoji} {a.name}{tier_display}**",
                value=f">>> {a.desc}\n{reward_display}{bar} `{p[0]}/{p[1]}`",
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
    @commands.slash_command()
    async def profile(self, ctx, user: opt_user()):
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
    @commands.slash_command()
    async def graph(self, ctx, user: opt_user()):
        """See a graph of a user's typing scores"""
        await self.handle_graph_cmd(ctx, user)

    @cooldown(5, 2)
    @commands.user_command(name="Typing Graph")
    async def graph_user(self, ctx, member: discord.Member):
        await self.handle_graph_cmd(ctx, member)

    async def handle_graph_cmd(self, ctx, user):
        user = await user_check(ctx, user)

        view = GraphView(ctx, user)
        await view.start()

    @cooldown(6, 2)
    @commands.slash_command()
    async def leaderboard(self, ctx):
        """See the top users in any category"""

        user = await self.bot.mongo.fetch_user(ctx.author)

        view = LeaderboardView(ctx, user)
        await view.start()

    @cooldown(5, 2)
    @commands.slash_command()
    async def achievements(self, ctx):
        """See all the achievements"""
        user_data = await self.bot.mongo.fetch_user(ctx.author)

        view = AchievementsView(ctx, user_data)

        await view.start()

    @cooldown(5, 2)
    @commands.slash_command()
    async def challenges(self, ctx):
        """View the daily challenges and your progress on them"""

        user = await ctx.bot.mongo.fetch_user(ctx.author)

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

        if not cmd_run_before(ctx, user):
            await ctx.followup.send(
                "Challenges restart at the same time every day!", ephemeral=True
            )

    @cooldown(6, 2)
    @commands.slash_command()
    async def season(self, ctx):
        """Information about the monthly season and your progress in it"""
        user = await self.bot.mongo.fetch_user(ctx.author)

        view = SeasonView(ctx, user)
        await view.start()

    @cooldown(6, 2)
    @commands.slash_command()
    async def scores(self, ctx, user: opt_user()):
        """View and download a user's recent typing scores"""
        user_data = await user_check(ctx, user)

        if len(user_data.scores) == 0:
            embed = ctx.error_embed(
                title=f"{icons.caution} User does not have any scores saved",
                description="Complete at least 1 typing test or race",
            )
            return await ctx.respond(embed=embed)

        view = ScoreView(ctx, user_data)

        await view.start()


def setup(bot):
    bot.add_cog(Bot(bot))
