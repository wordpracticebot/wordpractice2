import constants
from discord.ext import commands
from helpers.converters import opt_colour


class Misc(commands.Cog):
    """Miscellaneous commands"""

    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command(guild_ids=constants.GUILDS)
    async def ping(self, ctx):
        """View the bot's latency"""

        # Discord API latency
        latency = round(self.bot.latency * 1000, 3)

        embed = self.bot.embed(title=f"Pong! {latency} ms", add_footer=False)

        await ctx.respond(embed=embed)

    @commands.slash_command(guild_ids=constants.GUILDS)
    async def help(self, ctx):
        pass


def setup(bot):
    bot.add_cog(Misc(bot))
