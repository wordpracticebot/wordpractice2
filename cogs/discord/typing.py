from discord.commands import Option, SlashCommandGroup
from discord.ext import commands

import word_list

MAX_RACE_JOIN = 10
TEST_RANGE = (1, 100)

# Arguments
word_amt = lambda: Option(
    int,
    f"Choose a word amount from {TEST_RANGE[0]}-{TEST_RANGE[1]}",
    required=True,
)
quote_amt = lambda: Option(
    str,
    "Choose a quote length",
    choices=list(word_list.quotes["lengths"].keys()),
    required=True,
)


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
        await self.handle_dictionary_input(ctx, length)

    @tt_group.command()
    async def quote(self, ctx, length: quote_amt()):
        """Take a quote typing test"""
        await self.handle_quote_input(ctx, length)

    @race_group.command()
    async def dictionary(self, ctx, length: word_amt()):
        """Take a multiplayer dictionary typing test"""
        await self.handle_dictionary_input(ctx, length)

    @race_group.command()
    async def quote(self, ctx, length: quote_amt()):
        """Take a multiplayer quote typing test"""
        await self.handle_quote_input(ctx, length)

    async def handle_dictionary_input(self, ctx, length: int):
        if length not in range(*TEST_RANGE):
            raise commands.BadArgument(
                f"The typing test must be between {TEST_RANGE[0]} and {TEST_RANGE[1]} words"
            )

        # TODO: generate quote

    async def handle_quote_input(self, ctx, length: str):
        # TODO: generate quote
        pass


def setup(bot):
    bot.add_cog(Typing(bot))
