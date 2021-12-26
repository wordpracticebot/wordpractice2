from discord.ext import commands
from discord.commands import SlashCommandGroup
from helpers.converters import word_amt, quote_amt

MAX_RACE_JOIN = 10


class Typing(commands.Cog):
    """Typing test related commands"""

    def __init__(self, bot):
        self.bot = bot

    tt_group = SlashCommandGroup("tt", "Take a typing test")
    race_group = SlashCommandGroup(
        "race",
        f"Take a multiplayer typing test. Up to {MAX_RACE_JOIN} other users can join your race.",
    )

    @tt_group.command()
    async def dictionary(self, ctx, length: word_amt()):
        """Take a dictionary typing test"""
        pass

    @tt_group.command()
    async def quote(self, ctx, length: quote_amt()):
        """Take a quote typing test"""
        pass

    @race_group.command()
    async def dictionary(self, ctx, length: word_amt()):
        """Take a multiplayer dictionary typing test"""
        pass

    @race_group.command()
    async def quote(self, ctx, length: quote_amt()):
        """Take a multiplayer quote typing test"""
        pass


def setup(bot):
    bot.add_cog(Typing(bot))
