import re
import word_list

import discord
from discord.commands import Option
from discord.ext import commands
from PIL import ImageColor

RGB_STRING = re.compile(
    r"^\(?(0|255|25[0-4]|2[0-4]\d|1\d\d|0?\d?\d),(0|255|25[0-4]|2[0-4]\d|1\d\d|0?\d?\d),(0|255|25[0-4]|2[0-4]\d|1\d\d|0?\d?\d)\)?$"
)


class HexOrRGB(commands.Converter):
    async def convert(self, colour: str):
        try:
            return ImageColor.getrgb(colour)
        except ValueError:
            if RGB_STRING.match(colour):
                # Removing brackets
                colour = colour.translate({40: "", 41: ""})
                return [int(c) for c in colour.split(",")]

        raise commands.BadArgument(f'"{colour}" is not a valid rgb or hex colour')


# Commonly used arguments using functions to work with groups

# Users
opt_user = lambda: Option(
    discord.User, "Enter a user or user id", required=False, default=None
)
rqd_user = lambda: Option(discord.User, "Enter a user or user id", required=True)

# Colours
rqd_colour = lambda: Option(HexOrRGB, "Enter a hex or rgb colour", required=True)

# Typing test dictionary amount
word_amt = lambda: Option(
    int,
    "Choose a word amount from 1-100",
    autocomplete=discord.utils.basic_autocomplete(list(range(10, 101, 10))),
    required=True,
)
quote_amt = lambda: Option(
    str,
    "Choose a quote length",
    choices=list(word_list.quotes["lengths"].keys()),
    required=True,
)
