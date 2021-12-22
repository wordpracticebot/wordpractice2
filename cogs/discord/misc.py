from discord.ext import commands


class Misc(commands.Cog):
    """Miscellaneous commands"""

    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command()
    async def ping(self, ctx):
        """View the bot's latency"""

        # Discord API latency
        latency = round(self.bot.latency * 1000, 3)

        embed = self.bot.embed(title=f"Pong! {latency} ms", add_footer=False)

        await ctx.respond(embed=embed)

    @commands.slash_command()
    async def help(self, ctx):
        """List of commands"""
        pass

    @commands.slash_command()
    async def stats(self, ctx):
        pass

    @commands.slash_command()
    async def privacy(self, ctx):
        pass

    @commands.slash_command()
    async def invite(self, ctx):
        pass

    @commands.slash_command()
    async def rules(self, ctx):
        pass

    @commands.slash_command()
    async def vote(self, ctx):
        pass


def setup(bot):
    bot.add_cog(Misc(bot))
