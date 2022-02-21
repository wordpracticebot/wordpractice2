from discord.commands import permissions
from discord.ext import commands

from constants import MODERATOR_ROLE_NAME, SUPPORT_SERVER_ID


class Moderator(commands.Cog):
    """Commands only for moderators..."""

    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(guild_ids=[SUPPORT_SERVER_ID], default_permission=False)
    @permissions.has_role(MODERATOR_ROLE_NAME)
    async def test(self, ctx):
        await ctx.respond("test")


def setup(bot):
    bot.add_cog(Moderator(bot))
