from discord.commands import permissions
from discord.ext import commands

from constants import MODERATOR_ROLE_NAME, SUPPORT_SERVER_ID


class Moderator(commands.Cog):
    """Commands only for moderators..."""

    def __init__(self, bot):
        self.bot = bot

    # TODO: only enable for users who are moderators
    @commands.slash_command(guild_ids=[SUPPORT_SERVER_ID], default_permission=False)
    async def test(self, ctx):
        await ctx.respond("test")


def setup(bot):
    bot.add_cog(Moderator(bot))
