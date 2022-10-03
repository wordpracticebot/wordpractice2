import re
from typing import Union

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


class DatabaseUser(commands.UserConverter):
    @classmethod
    async def convert(cls, ctx, argument: str) -> Union[discord.User, str]:
        # Pycord: https://github.com/Pycord-Development/pycord

        match = cls._get_id_match(argument) or re.match(
            r"<@!?([0-9]{15,20})>$", argument
        )
        result = None
        state = ctx._state

        if match is not None:
            user_id = int(match.group(1))
            result = ctx.bot.get_user(user_id)
            if ctx.message is not None and result is None:
                result = discord.utils.get(ctx.message.mentions, id=user_id)
            if result is None:
                try:
                    result = await ctx.bot.fetch_user(user_id)
                except discord.HTTPException:
                    raise commands.UserNotFound(argument) from None

            return result

        arg = argument

        # Remove the '@' character if this is the first character from the argument
        if arg[0] == "@":
            # Remove first character
            arg = arg[1:]

        # check for discriminator if it exists,
        if len(arg) > 5 and arg[-5] == "#":
            discrim = arg[-4:]
            name = arg[:-5]
            predicate = lambda u: u.name == name and u.discriminator == discrim
            result = discord.utils.find(predicate, state._users.values())
            if result is not None:
                return result

            return name, discrim

        raise commands.UserNotFound(argument)


# Commonly used arguments using functions to work with groups

# Users
user_option = discord.option(
    "user", DatabaseUser, description="Enter a user mention, id or name#discriminator"
)
discord_user_option = discord.option(
    "user", discord.User, description="Enter a user mention or id"
)

# Colours
colour_option = lambda name: discord.option(
    name, HexOrRGB, description="Enter a hex or rgb colour"
)
