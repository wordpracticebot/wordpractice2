import time
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from bot import Context
from data.constants import PREMIUM_LINK
from helpers.ui import create_link_view
from helpers.utils import get_command_name, invoke_completion

if TYPE_CHECKING:
    from cogs.utils.mongo import User


def premium_command():
    async def predicate(ctx: Context):
        if ctx.initial_user.is_premium is False:
            view = create_link_view({"Upgrade": PREMIUM_LINK})

            embed = ctx.error_embed(
                title="Premium Command",
                description=f"Only **[Premium Members]({PREMIUM_LINK})** can use this feature!",
            )

            await ctx.respond(embed=embed, view=view)

            invoke_completion(ctx)

            return False

        return True

    return commands.check(predicate)


def cooldown(regular: int, premium: int):
    async def predicate(ctx: Context):
        # Cooldown key
        c = (ctx.author.id, get_command_name(ctx.command))

        # Checking if there is a cooldown
        cooldown = ctx.bot.cooldowns.get(c)

        user = ctx.initial_user

        if cooldown:
            # Checking if cooldown has expired
            if time.time() <= cooldown:
                embed = ctx.error_embed(
                    title="Command On Cooldown",
                    description=f"Try again in **{round(abs(time.time() - cooldown), 2)}** seconds",
                )

                if user.is_premium is False and regular > premium:
                    embed.description += f"\n\n**[Premium Members]({PREMIUM_LINK})** only wait **{premium}s** instead of **{regular}s**!"

                    view = create_link_view({"Upgrade": PREMIUM_LINK})
                else:
                    view = None

                await ctx.respond(embed=embed, view=view)

                return False

        # Giving cooldown based off account type

        c_time = time.time()

        if user.premium:
            c_time += premium
        else:
            c_time += regular

        ctx.bot.cooldowns[c] = c_time

        return True

    return commands.check(predicate)


async def user_check(ctx: Context, user: "User"):
    """Handles the user inputted and fetches user"""
    if isinstance(user, (discord.User, discord.Member)) and user.bot:
        raise commands.BadArgument("`Beep boop!` That user is a bot :robot:")

    if user is None:
        user = ctx.initial_user
    else:
        user = await ctx.bot.mongo.fetch_user(user)

    if user is None:
        raise commands.BadArgument(
            "User not in database, have they used wordPractice before?"
        )

    return user
