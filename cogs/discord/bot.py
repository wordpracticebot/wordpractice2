import discord
from discord.ext import commands
from discord.utils import escape_markdown

from achievements import categories, get_achievement_tier, get_bar
from achievements.challenges import get_daily_challenges
from constants import LB_LENGTH, UPDATE_24_HOUR_INTERVAL
from helpers.checks import cooldown, user_check
from helpers.converters import opt_user
from helpers.ui import BaseView, DictButton, ScrollView, ViewFromDict

LB_OPTIONS = [
    {
        "label": "Alltime",
        "emoji": "\N{EARTH GLOBE AMERICAS}",
        "desc": "Coins, Words Typed",
        "options": ["Coins", "Words Typed"],
        "default": 1,
    },
    {
        "label": "Monthly Season",
        "emoji": "\N{SPORTS MEDAL}",
        "desc": "XP",
        "options": ["XP"],
        "default": 0,
    },
    {
        "label": "24 Hour",
        "emoji": "\N{CLOCK FACE ONE OCLOCK}",
        "desc": "XP, Words Typed",
        "options": ["XP", "Words Typed"],
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


class LeaderboardSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
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

    async def callback(self, interaction):
        pass


class LeaderboardView(ScrollView):
    def __init__(self, ctx, user):
        super().__init__(ctx, int(LB_LENGTH / 10), row=2, compact=False)

        self.user = user
        self.category = 1  # Starting on season category

    async def create_page(self):
        return self.ctx.embed(title=f"Page {self.page}")

    async def jump_to_placing(self, button, interaction):
        pass

    async def start(self):
        selector = LeaderboardSelect()

        # Cannot user decorator because it's added before scroll items are added and they are on the same row
        btn = discord.ui.Button(
            label="Jump to Placing",
            style=discord.ButtonStyle.grey,
            row=2,
        )
        btn.callback = self.jump_to_placing

        self.add_item(selector)
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
        embed = self.ctx.embed(title=self.user.display_name, add_footer=False)
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

        tier = None

        embed = self.ctx.embed(title=f"{self.page}", description=c.desc)

        for a in c.challenges:
            tier = None
            # Tiers
            if isinstance(a, list):
                names = [m.name for m in a]

                tier = get_achievement_tier(self.user, names)

                a = a[tier]

            p = a.progress(self.user)

            bar = get_bar(p[0] / p[1])

            embed.add_field(
                name=a.name
                + (f" `[{tier + 1}/{len(names)}]`" if tier is not None else ""),
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
        c = get_daily_challenges()
        print(c)
        # TODO: display daily challenges


def setup(bot):
    bot.add_cog(Bot(bot))
