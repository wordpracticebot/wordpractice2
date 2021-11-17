from datetime import datetime

from discord.ext import commands


class Bot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(aliases=["latency"])
    async def ping(self, ctx):
        """View the bot's latency"""

        # Discord API latency
        latency = round(self.bot.latency * 1000, 3)

        embed = self.bot.embed(title=f"Pong! {latency} ms", add_footer=False)

        await ctx.reply(embed=embed)


def setup(bot):
    bot.add_cog(Bot(bot))
