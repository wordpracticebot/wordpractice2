import discord
from discord.ext import commands

from achievements import categories, get_achievement_tier, get_bar
from helpers.checks import cooldown
from helpers.converters import opt_user
from helpers.ui import BaseView, DictButton, ViewFromDict


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
        return self.callbacks[self.page][1]()

    def general_page(self):
        embed = self.ctx.embed(title="stats page", description="hello")
        return embed

    def create_achievements_page(self):
        embed = self.ctx.embed(title="achievements page", description="hello")
        return embed

    def create_stats_page(self):
        embed = self.ctx.embed(title="stats page", description="hello")
        return embed

    def create_typing_page(self):
        embed = self.ctx.embed(title="typing page", description="hello")
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

    async def user_check(self, ctx, user):
        """Handles the user inputted and fetches user"""
        if isinstance(user, (discord.User, discord.Member)) and user.bot:
            raise commands.BadArgument("That user is a bot :robot:")

        if user is None:
            user = ctx.author

        user = await self.bot.mongo.fetch_user(user)

        if user is None:
            raise commands.BadArgument("User not in database")

        return user

    @cooldown(8, 2)
    @commands.slash_command()
    async def profile(self, ctx, user: opt_user()):
        """View user statistics"""
        await self.handle_profile_cmd(ctx, user)

    @cooldown(8, 2)
    @commands.user_command(name="Typing Profile")
    async def profile_user(self, ctx, member: discord.Member):
        await self.handle_profile_cmd(ctx, member)

    async def handle_profile_cmd(self, ctx, user):
        user = await self.user_check(ctx, user)

        view = ProfileView(ctx, user)

        await view.start()

    @commands.slash_command()
    async def graph(self, ctx, user: opt_user()):
        """See a graph of a user's typing scores"""
        user = await self.user_check(ctx, user)

    @commands.slash_command()
    async def leaderboard(self, ctx):
        """See the top users in any category"""
        pass

    @commands.slash_command()
    async def highscore(self, ctx):
        """See the fastest users in any typing category"""
        pass

    @commands.slash_command()
    async def achievements(self, ctx):
        """See all the achievements"""
        user_data = await self.bot.mongo.fetch_user(ctx.author)

        view = AchievementsView(ctx, user_data)

        await view.start()

    @commands.slash_command()
    async def challenges(self, ctx):
        """View the daily challenges and your progress on them"""
        pass


def setup(bot):
    bot.add_cog(Bot(bot))
