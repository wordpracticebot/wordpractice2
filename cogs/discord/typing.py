import json
import random
from itertools import cycle, islice

import discord
from discord.commands import SlashCommandGroup
from discord.ext import commands

import word_list
from constants import MAX_RACE_JOIN, TEST_RANGE
from helpers.converters import quote_amt, word_amt


def load_test_file(name):
    with open(f"./word_list/{name}", "r") as f:
        return json.load(f)


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
        quote = await self.handle_dictionary_input(ctx, length)

    @tt_group.command()
    async def quote(self, ctx, length: quote_amt()):
        """Take a quote typing test"""
        quote = await self.handle_quote_input(ctx, length)

    @race_group.command()
    async def dictionary(self, ctx, length: word_amt()):
        """Take a multiplayer dictionary typing test"""
        quote = await self.handle_dictionary_input(ctx, length)

    @race_group.command()
    async def quote(self, ctx, length: quote_amt()):
        """Take a multiplayer quote typing test"""
        quote = await self.handle_quote_input(ctx, length)

    @commands.user_command(name="Typing Challenge")
    async def race_challenge(self, ctx, member: discord.Member):
        # TODO: send a dropdown to choose race
        pass

    async def handle_dictionary_input(self, ctx, length: int):
        if length not in range(*TEST_RANGE):
            raise commands.BadArgument(
                f"The typing test must be between {TEST_RANGE[0]} and {TEST_RANGE[1]} words"
            )

        user = await self.bot.mongo.fetch_user(ctx.author)

        words = load_test_file(word_list.languages[user.lang]["levels"][user.level])

        return random.sample(words, length)

    async def handle_quote_input(self, ctx, length: str):
        test_range = word_list.quotes["lengths"][length]

        quotes = load_test_file("quotes.json")

        start = random.randint(0, len(quotes) - 1)

        # Selecting consecutive items from list of sentences
        return list(islice(cycle(quotes), start, start + random.randint(*test_range)))

    async def do_typing_test(self, quote):
        pass

    async def do_race(self, quote):
        pass


def setup(bot):
    bot.add_cog(Typing(bot))
