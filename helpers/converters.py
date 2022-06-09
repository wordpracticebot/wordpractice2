import re

import discord
from discord.ext import commands
from PIL import ImageColor

RGB_STRING = re.compile(
    r"^\(?(0|255|25[0-4]|2[0-4]\d|1\d\d|0?\d?\d),(0|255|25[0-4]|2[0-4]\d|1\d\d|0?\d?\d),(0|255|25[0-4]|2[0-4]\d|1\d\d|0?\d?\d)\)?$"
)


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
    "user", discord.User, description="Enter a user or user id"
)

# Colours
colour_option = lambda name: discord.option(
    name, HexOrRGB, desc="Enter a hex or rgb colour"
)
