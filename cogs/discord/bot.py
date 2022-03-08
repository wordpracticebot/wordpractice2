import discord
from discord.ext import commands

import icons
from achievements import categories, get_achievement_tier, get_bar
from achievements.challenges import get_daily_challenges
from constants import LB_DISPLAY_AMT
from helpers.checks import cooldown, user_check
from helpers.converters import opt_user
from helpers.ui import BaseView, DictButton, ScrollView, ViewFromDict

LB_OPTIONS = [
    {
        "label": "Alltime",
        "emoji": "\N{EARTH GLOBE AMERICAS}",
        "desc": "Words Typed, Daily Streak",
        "options": ["Words Typed", "Daily Streak"],
        "default": 1,
    },
    {
        "label": "Monthly Season",
        "emoji": "\N{SPORTS MEDAL}",
        "desc": "Experience",
        "options": ["Experience"],
        "default": 0,
    },
    {
        "label": "24 Hour",
        "emoji": "\N{CLOCK FACE ONE OCLOCK}",
        "desc": "Experience, Words Typed",
        "options": ["Experience", "Words Typed"],
        "default": 0,
    },
    {
        "label": "High Score",
        "emoji": "\N{RUNNER}",
        "desc": "Short, Medium and Long Test",
        "options": ["Short", "Medium", "Long"],
        "default": 1,
    },
]


class LeaderboardView(ScrollView):
    def __init__(self, ctx, user):
        super().__init__(ctx, int(LB_DISPLAY_AMT / 10), row=2, compact=False)

        self.timeout = 60

        self.user = user

        self.category = 1  # Starting on season category

        self.stat = LB_OPTIONS[self.category]["default"]
        self.placing = None

        self.active_btns = []

    @discord.ui.select(
        placeholder="Select a category...",
        min_values=1,
        max_values=1,
        options=[
            discord.SelectOption(
                label=n["label"],
                emoji=n["emoji"],
                description=n["desc"],
                value=str(i),
            )
            for i, n in enumerate(LB_OPTIONS)
        ],
        row=0,
    )
    async def callback(self, select, interaction):
        value = int(select.values[0])

        self.stat = LB_OPTIONS[value]["default"]

        self.page = 0
        # TODO: can this be removed
        self.placing = None
        self.category = value

        await self.update_all(interaction)

    # TODO: add image generation for the leaderboard command
    def gen_lb_image(self):
        pass

    async def create_page(self):
        # Getting the placing
        return self.ctx.embed(title=f"Page {self.page} {self.category} {self.stat}")

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
        self.stat = stat
        self.page = 0

        await self.update_all(interaction)

    def get_active_btns(self):
        return [c for c in self.children if c.row == 1]

    def add_metric_buttons(self):
        metrics = LB_OPTIONS[self.category]["options"]

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
        base_embed = self.get_base_embed(self.page)

        return self.callbacks[self.page][1](base_embed)

    def get_base_embed(self, page_name):
        embed = self.ctx.embed(title=self.user.display_name)
        embed.set_author(
            name=f"{self.user.username} | {page_name}",
            icon_url=self.user.avatar_url,
        )
        return embed

    def general_page(self, embed):
        return embed

    def create_achievements_page(self, embed):
        return embed

    def create_stats_page(self, embed):
        return embed

    def create_typing_page(self, embed):
        return embed

    def get_embed_callbacks(self):
        return {
            "General": ["\N{GRINNING FACE}", self.general_page],
            "Achievements": ["\N{SHIELD}", self.create_achievements_page],
            "Statistics": ["\N{BAR CHART}", self.create_stats_page],
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

        for a in c.challenges:
            tier_display = ""
            # Tiers
            if isinstance(a, list):
                all_names = [m.name for m in a]

                names = list(set(all_names))

                tier = get_achievement_tier(self.user, names)

                a = a[tier]

                tier_display = f" `[{tier + 1}/{len(all_names)}]`"

            p = a.progress(self.user)

            bar = get_bar(p[0] / p[1])

            emoji = icons.success if p[0] >= p[1] else icons.danger

            embed.add_field(
                name=f"{emoji} {a.name}" + tier_display,
                value=(f">>> {a.desc}\n**Reward:** {a.reward}\n{bar} `{p[0]}/{p[1]}`"),
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

        challenges, xp = get_daily_challenges()

        embed = ctx.embed(
            title="Daily Challenges",
            description=f"Complete all the daily challenges to earn:\n{icons.xp} **{xp} xp**\n\n** **",
        )

        for c in challenges:
            # Getting the user's progress on the challenge
            p = c.progress(user)

            # Generating the progress bar
            bar = get_bar(p[0] / p[1])

            emoji = icons.success if p[0] >= p[1] else icons.danger

            embed.add_field(
                name=f"{emoji} {c.title}",
                value=f"> {c.description}\n> {bar} `{p[0]}/{p[1]}`",
                inline=False,
            )

        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(Bot(bot))
