import time
from datetime import datetime, timezone

import discord
import humanize
from discord.ext import commands

import icons
from achievements import categories, get_achievement_tier, get_bar
from achievements.challenges import get_daily_challenges
from constants import COMPILE_INTERVAL, LB_DISPLAY_AMT, LB_LENGTH
from helpers.checks import cooldown, user_check
from helpers.converters import opt_user
from helpers.ui import BaseView, DictButton, ScrollView, ViewFromDict
from helpers.user import get_typing_average
from helpers.utils import calculate_consistency


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

        self.stat = self.view.lb.default

        await self.view.update_all(interaction)


class LeaderboardView(ScrollView):
    def __init__(self, ctx, user):
        super().__init__(ctx, int(LB_DISPLAY_AMT / 10), row=2, compact=False)

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
            title=f"{c.name} Leaderboard | Page {self.page + 1}",
            description=f"The leaderboard updates again in <t:{time_until_next_update}:R>",
        )

        for i, u in enumerate(c.data[self.page * 10 : (self.page + 1) * 10]):
            p = self.page * 10 + i

            extra = ""

            if self.placing is None and u["_id"] == self.user.id:
                self.placing = p
                extra = "__"

            username = f"{u['name']}{u['discriminator']} {u['status']}"

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
        else:
            place_display = self.placing + 1

        # Adding author's own placing at the bottom

        # TODO: add counts and make them show even if user is outside of calculated
        count = 0

        embed.add_field(
            name=f"`{place_display}.` {self.user.display_name} - {count} {c.unit}",
            value="** **",
            inline=False,
        )

        return embed

    async def jump_to_placing(self, button, interaction):
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
            for i in metrics[active_amt:]:
                btn = discord.ui.Button(
                    row=1,
                )
                btn.callback = lambda interaction: self.change_stat(interaction, i)
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
        # Getting the correct leaderboard
        placing = self.ctx.bot.lbs[category].stats[stat].get_placing(user.id)

        if placing is None:
            return f"(> {LB_LENGTH})"

        if placing == 1:
            return ":first_place:"

        if placing == 2:
            return ":second_place:"

        if placing == 3:
            return ":third_place:"

        return f"({humanize.ordinal(placing)})"

    def create_achievements_page(self, embed):
        return embed

    def create_stats_page(self, embed):
        embed.set_thumbnail(url="https://i.imgur.com/KrXiy9S.png")

        ts = "\N{THIN SPACE}"

        embed.title += f"\n\nAccount{ts*34}Season{ts*30}24h{ts*15}** **"

        # TODO; add proper spacing
        for group in (
            (
                f"**Words**: {self.user.words:,}",
                f"**XP:** {self.user.xp:,}",
                f"**Words:** {sum(self.user.last24[0]):,}",
            ),
            (f"**XP:** {self.user.last24[1]:,}"),
        ):
            pass

        if self.user.badges == []:
            badges = "They have no badges..."
        else:
            badges = " ".join(self.user.badges)

        embed.description = (
            "there is going to be something here soon\n\n"
            f"**Badges ({len(self.user.badges)})**\n"
            f"{badges}"
        )

        embed.add_field(
            name=f"Trophies ({sum(self.user.trophies)})",
            value=f"{ts*8}".join(
                f"{icons.trophies[i]} x{t}" for i, t in enumerate(self.user.trophies)
            ),
            inline=False,
        )

        return embed

    def create_typing_page(self, embed):
        embed.set_thumbnail(url="https://i.imgur.com/BZzMGjc.png")
        embed.add_field(
            name="High Scores",
            value="Scores are divided by word count range",
            inline=False,
        )

        hs1, hs2, hs3 = self.user.highspeed.values()

        ts = "\N{THIN SPACE}"

        # Short high score
        placing = self.get_placing_display(self.user, 3, 0)

        embed.add_field(
            name=f"Range:{ts*20}10-20:",
            value=(
                f"Wpm:{ts*22}{hs1.wpm}\n"
                f"Accuracy:{ts*11}{hs1.acc}%\n"
                f"Placing:{ts*17}**{placing}**"
            ),
        )

        # Medium high score
        placing = self.get_placing_display(self.user, 3, 1)

        embed.add_field(
            name="21-50:",
            value=(f"{hs2.wpm}\n{hs2.acc}%\n**{placing}**"),
        )

        placing = self.get_placing_display(self.user, 3, 2)

        embed.add_field(
            name="21-50:",
            value=(f"{hs3.wpm}\n{hs3.acc}%\n**{placing}**"),
        )

        wpm, raw, acc, cw, tw, scores = get_typing_average(self.user, 10)

        if len(scores) > 1:
            con = calculate_consistency([s.wpm for s in scores])
        else:
            con = 0

        # Average

        wpm_perc = self.get_perc_sign(wpm * len(scores), self.ctx.bot.avg_perc[0])
        raw_perc = self.get_perc_sign(raw * len(scores), self.ctx.bot.avg_perc[1])
        acc_perc = self.get_perc_sign(acc * len(scores), self.ctx.bot.avg_perc[2])

        # Consistency percentile is based on arbitrary values
        con_perc = "+" if con >= 75 else "/" if con >= 50 else "-"

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

        return embed

    def get_embed_callbacks(self):
        return {
            "Statistics": ["\N{BAR CHART}", self.create_stats_page],
            "Typing": ["\N{KEYBOARD}", self.create_typing_page],
            "Achievements": ["\N{SHIELD}", self.create_achievements_page],
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

        self.view.page = option

        await self.view.update_message(interaction)


class AchievementsButton(DictButton):
    def __init__(self, label, user):
        style = (
            discord.ButtonStyle.success
            if categories[label].is_completed(user)
            else discord.ButtonStyle.danger
        )

        super().__init__(label=label, style=style)

    def toggle_success(self):
        self.disabled = True

    def toggle_regular(self):
        self.disabled = False


class AchievementsView(ViewFromDict):
    def __init__(self, ctx, user):
        super().__init__(ctx, categories)

        self.user = user  # user data

    def button(self, label):
        return AchievementsButton(label, self.user)

    async def create_page(self):
        c = self.the_dict[self.page]

        embed = self.ctx.embed(title=f"{self.page}", description=c.desc)

        content = ""

        for a in c.challenges:
            tier_display = ""
            # Tiers
            if isinstance(a, list):
                all_names = [m.name for m in a]

                names = set(all_names)

                tier = get_achievement_tier(self.user, names)

                a = a[tier]

                tier_display = f" `[{tier + 1}/{len(all_names)}]`"

            p = a.progress(self.user)

            bar = get_bar(p[0] / p[1])

            emoji = icons.success if p[0] >= p[1] else icons.danger

            content += (
                f"**{emoji} {a.name}{tier_display}**\n"
                f"> {a.desc}\n"
                f"> **Reward:** {a.reward.desc}\n"
                f"> {bar} `{p[0]}/{p[1]}`\n\n"
            )

        embed.add_field(
            name="** **",
            value=content,
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

        unix_timestamp = int(time.mktime(end_of_today.timetuple()))

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
            p = c.progress(user)

            # Generating the progress bar
            bar = get_bar(p[0] / p[1])

            emoji = icons.success if p[0] >= p[1] else icons.danger

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

    @cooldown(6, 2)
    @commands.slash_command()
    async def season(self, ctx):
        # TODO: write a description here
        pass


def setup(bot):
    bot.add_cog(Bot(bot))
