import discord
from discord.ext import commands

from achievements import categories, get_achievement_tier, get_bar
from helpers.checks import cooldown
from helpers.converters import opt_user
from helpers.ui import DictButton, PageView, ViewFromDict


class ProfileView(PageView):
    def __init__(self, ctx, user):
        super().__init__(ctx)

        self.page = 0
        self.user = user

    async def create_stats_page(self):
        embed = self.ctx.embed(title="stats page", description="hello")

        return embed

    async def create_account_page(self):
        embed = self.ctx.embed(title="account page", description="hello")

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


class User(commands.Cog):
    """Essential bot commands"""

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
            raise commands.BadArgument("User not found")

        return user

    @cooldown(8, 2)
    @commands.slash_command()
    async def profile(self, ctx, user: opt_user()):
        """View user statistics"""
        await self.handle_profile_cmd(ctx, user)

    @cooldown(8, 2)
    @commands.user_command(name="Typing Profile")
    async def profile(self, ctx, member: discord.Member):
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
        """See the fastest users in any category"""
        pass

    @commands.slash_command()
    async def achievements(self, ctx):
        """See all the achievements"""
        user_data = await self.bot.mongo.fetch_user(ctx.author)

        view = AchievementsView(ctx, user_data)

        await view.start()

    @commands.slash_command()
    async def challenges(self, ctx):
        """View the daily challenge and your progress on it"""
        pass


def setup(bot):
    bot.add_cog(User(bot))
