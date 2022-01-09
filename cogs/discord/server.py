from discord.ext import commands


class Server(commands.Cog):
    """Commands for the community server"""

    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command()
    async def roles(self, ctx):
        """Update your wordPractice roles on the server"""
        pass


def setup(bot):
    bot.add_cog(Server(bot))
