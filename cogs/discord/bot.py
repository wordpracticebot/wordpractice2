import discord
from discord.ext import commands

from achievements import categories
from constants import BAR_SIZE, PROGRESS
from helpers.converters import opt_user
from helpers.ui import PageView, ViewFromDict


class ProfileView(PageView):
    def __init__(self, ctx, user):
        super().__init__(ctx)

        self.page = 0
        self.user = user

    async def create_stats_page(self):
        embed = self.ctx.bot.embed(title="stats page", description="hello")

        return embed

    async def create_account_page(self):
        embed = self.ctx.bot.embed(title="account page", description="hello")

        return embed

    async def update_message(self, interaction):
        embed = await self.create_page()
        await interaction.message.edit(embed=embed, view=self)

    async def create_page(self):
        if self.page == 0:
            embed = await self.create_stats_page()
        elif self.page == 1:
            embed = await self.create_account_page()

        return embed

    async def update_buttons(self, page):
        self.children[self.page].style = discord.ButtonStyle.primary
        self.children[page].style = discord.ButtonStyle.success

        self.page = page

    async def update_all(self, interaction, page):
        await self.update_buttons(page)
        await self.update_message(interaction)

    async def start(self):
        embed = await self.create_page()
        self.response = await self.ctx.respond(embed=embed, view=self)

    @discord.ui.button(label="Statistics", style=discord.ButtonStyle.success)
    async def stats_page(self, button, interaction):
        if self.page != 0:
            await self.update_all(interaction, 0)

    @discord.ui.button(label="Account", style=discord.ButtonStyle.primary)
    async def account_page(self, button, interaction):
        if self.page != 1:
            await self.update_all(interaction, 1)


class AchievementsView(ViewFromDict):
    def __init__(self, ctx, the_dict, user):
        super().__init__(ctx, the_dict)

        self.user = user  # user data

    @staticmethod
    def get_bar(p):
        bar = ""
        for i in range(BAR_SIZE):
            if i == 0:
                bar += PROGRESS[0][int(p != 0)]
            elif i == BAR_SIZE - 1:
                bar += PROGRESS[2][int(p >= BAR_SIZE)]
            else:
                bar += PROGRESS[1][2 if i == p else int(i > p)]

        return bar

    async def create_page(self):
        c = self.the_dict[self.page]

        tier = None

        embed = self.ctx.bot.embed(title=f"{self.page}", description=c.desc)

        spacing = " " * 5

        for a in c.challenges:
            tier = None
            # Tiers
            if isinstance(a, list):
                names = [m.name for m in a]

                user_a = set(self.user.achievements)

                if names[-1] in user_a or names[-2] in user_a:
                    tier = len(names) - 1
                if user_a.isdisjoint(names):
                    tier = 0
                else:
                    # getting the highest achievement in tier that user has
                    tier = sorted([names.index(x) for x in set(names) & user_a])[-1] + 1

                a = a[tier]

            progress = a.progress(self.user)

            bar = self.get_bar(int(progress * BAR_SIZE))

            embed.add_field(
                name=a.name
                + (f" `[{tier + 1}/{len(names)}]`" if tier is not None else ""),
                value=(
                    f">>> {a.desc}\n**Reward:** {a.reward}{spacing}\n"
                    f"{bar} `{min(round(progress*100, 2), 100)}%`"
                ),
            )

        return embed


class User(commands.Cog):
    """Essential bot commands"""

    def __init__(self, bot):
        self.bot = bot

    async def user_check(self, ctx, user):
        """Handles the user inputted and fetches user"""
        if isinstance(user, (discord.User, discord.Member)) and user.bot:
            raise commands.BadArgument("That user is a bot")

        if user is None:
            user = ctx.author

        user = await self.bot.mongo.fetch_user(user)

        if user is None:
            raise commands.BadArgument("User not found")

        return user

    @commands.slash_command()
    async def profile(self, ctx, user: opt_user()):
        """View user statistics"""
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
        """See the fastest users in any category"""
        pass

    @commands.slash_command()
    async def achievements(self, ctx):
        """See all the achievements"""
        user_data = await self.bot.mongo.fetch_user(ctx.author)

        view = AchievementsView(ctx, categories, user_data)

        await view.start()


def setup(bot):
    bot.add_cog(User(bot))
