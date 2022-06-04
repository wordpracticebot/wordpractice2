import re

import discord
from discord.commands import Option
from discord.ext import commands
from PIL import ImageColor

from constants import TEST_RANGE, TEST_ZONES

RGB_STRING = re.compile(
    r"^\(?(0|255|25[0-4]|2[0-4]\d|1\d\d|0?\d?\d),(0|255|25[0-4]|2[0-4]\d|1\d\d|0?\d?\d),(0|255|25[0-4]|2[0-4]\d|1\d\d|0?\d?\d)\)?$"
)

QUOTE_CHOICES = list(TEST_ZONES.keys())


class HexOrRGB(commands.Converter):
    async def convert(self, ctx, colour: str):
        try:
            return ImageColor.getrgb(colour)
        except ValueError:
            if RGB_STRING.match(colour):
                # Removing brackets
                colour = colour.translate({40: "", 41: ""})
                return [int(c) for c in colour.split(",")]

        raise commands.BadArgument(f'"{colour}" is not a valid rgb or hex colour')


def rgb_to_hex(r, g, b):
    return ("#{:02x}{:02x}{:02x}").format(r, g, b)


# Commonly used arguments using functions to work with groups

# Users
user_option = discord.option(
    name="user", type=discord.User, description="Enter a user or user id"
)

# Colours
colour_option = lambda name: discord.option(
    name=name, type=HexOrRGB, desc="Enter a hex or rgb colour"
)

# Arguments
word_option = discord.option(
    name="length",
    type=int,
    desc=f"Choose a word amount from {TEST_RANGE[0]}-{TEST_RANGE[1]}",
)

quote_option = discord.option(
    name="length",
    type=str,
    desc="Choose a quote length",
    choices=QUOTE_CHOICES,
)
