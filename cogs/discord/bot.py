import discord
from discord.ext import commands
from helpers.ui import BaseView
from helpers.converters import opt_user


class ProfileView(BaseView):
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


class User(commands.Cog):
    """User profile and statistic commands"""

    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command()
    async def profile(self, ctx, user: opt_user()):
        """View user statistics"""
        if user is None:
            user = ctx.author

        user = await self.bot.mongo.fetch_user(user)

        if user is None:
            raise commands.BadArgument("User not found")

        view = ProfileView(ctx, user)

        await view.start()


def setup(bot):
    bot.add_cog(User(bot))
