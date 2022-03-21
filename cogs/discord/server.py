import discord
from discord.ext import commands

from constants import SUPPORT_SERVER_ID
from helpers.checks import cooldown


class Server(commands.Cog):
    """Commands for the community server"""

    emoji = "\N{CLOUD}"
    order = 5

    def __init__(self, bot):
        self.bot = bot

    @cooldown(10, 3)
    @commands.slash_command(guild_ids=[SUPPORT_SERVER_ID])
    async def roles(self, ctx):
        """Update your wordPractice roles on the server"""
        pass


def setup(bot):
    bot.add_cog(Server(bot))
