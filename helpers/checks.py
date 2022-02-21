import time

from discord.ext import commands

from constants import PREMIUM_LAUNCHED, PREMIUM_LINK
from helpers.ui import create_link_view
from helpers.utils import format_slash_command


def cooldown(regular: int, premium: int):
    async def predicate(ctx):
        if ctx.testing:
            return True

        # Cooldown key
        c = (ctx.author.id, format_slash_command(ctx.command))

        # Checking if there is a cooldown
        cooldown = ctx.bot.cooldowns.get(c)

        user = await ctx.bot.mongo.fetch_user(ctx.author)

        if cooldown:
            # Checking if cooldown has expired
            if time.time() <= cooldown:
                embed = ctx.error_embed(
                    title="Command On Cooldown",
                    description=f"Try again in **{round(abs(time.time() - cooldown), 2)}** seconds",
                )

                if PREMIUM_LAUNCHED and user["premium"] is False and regular > premium:
                    embed.description += f"\n\n[Premium members]({PREMIUM_LINK}) only wait **{premium}s** instead of **{regular}s**!"

                    view = create_link_view({"Get Premium": PREMIUM_LINK})
                else:
                    view = None

                await ctx.respond(embed=embed, view=view)

                return False

        # Giving cooldown based off account type

        c_time = time.time()

        if user["premium"]:
            c_time += premium
        else:
            c_time += regular

        ctx.bot.cooldowns[c] = c_time

        return True

    return commands.check(predicate)
