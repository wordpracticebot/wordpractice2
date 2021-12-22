import re
import discord
from discord.ext import commands
from discord.commands import Option
from PIL import ImageColor
from functools import lru_cache

RGB_STRING = re.compile(
    r"^\(?(0|255|25[0-4]|2[0-4]\d|1\d\d|0?\d?\d),(0|255|25[0-4]|2[0-4]\d|1\d\d|0?\d?\d),(0|255|25[0-4]|2[0-4]\d|1\d\d|0?\d?\d)\)?$"
)


class HexOrRGB(commands.Converter):
    @lru_cache(maxsize=50)
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
opt_user = lambda: Option(discord.User, "Enter a user", required=False, default=None)
rqd_user = lambda: Option(discord.User, "Enter a user", required=True)

rqd_colour = lambda: Option(HexOrRGB, "Enter a hex or rgb colour", required=True)
