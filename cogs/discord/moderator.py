import discord
from discord.commands import Option
from discord.ext import commands

from constants import SUPPORT_SERVER_ID
from helpers.checks import user_check
from helpers.converters import rqd_user
from helpers.utils import datetime_to_unix

BAN_AUTOCOMPLETE = [
    "Cheating",
    "Trading",
    "Advertisement",
    "Exploiting",
    "Breaking Discord TOS",
]


class Moderator(commands.Cog):
    """Commands only for moderators..."""

    def __init__(self, bot):
        self.bot = bot

    # TODO: only enable for users who are moderators
    # TODO: add option to wipe the user
    @commands.slash_command(guild_ids=[SUPPORT_SERVER_ID])
    async def ban(
        self,
        ctx,
        user: rqd_user(),
        reason: Option(
            str,
            "Reason for the ban",
            autocomplete=discord.utils.basic_autocomplete(BAN_AUTOCOMPLETE),
        ),
        wipe: Option(bool, "Whether the user's account should be banned") = True,
    ):
        """Ban a user"""
        user_data = await user_check(ctx, user)

        if user_data.banned:
            raise commands.BadArgument("That user is already banned")

        await self.bot.mongo.ban_user(user, reason, ctx.author)

        embed = ctx.error_embed(
            title="User Banned",
            description=f"Reason: {reason}",
        )

        await ctx.respond(embed=embed)

    @commands.slash_command(guild_ids=[SUPPORT_SERVER_ID])
    async def unban(self, ctx, user: rqd_user()):
        """Unban a user"""
        user_data = await user_check(ctx, user)

        if user_data.banned is False:
            raise commands.BadArgument("That user is not banned")

        await self.bot.mongo.update_user(user.id, {"$set": {"banned": False}})

        embed = ctx.default_embed(title="User Unbanned")

        await ctx.respond(embed=embed)

    @commands.slash_command(guild_ids=[SUPPORT_SERVER_ID])
    async def cat(self, ctx, user: rqd_user()):
        """View the infractions of a user"""

        user_data = await user_check(ctx, user)

        embed = ctx.error_embed(
            title=f"{user_data.username}'s Infractions",
            description=f"**Ban Status:** {user_data.banned}",
        )

        # TODO: add pagination

        for i, inf in enumerate(user_data.infractions):
            timestamp = datetime_to_unix(inf.timestamp)

            embed.add_field(
                name=f"Infraction {i + 1}",
                value=(
                    f">>> Moderator: {inf.mod_name} ({inf.mod_id})\n"
                    f"Reason: {inf.reason}\n"
                    f"Timestamp: <t:{timestamp}:F>"
                ),
                inline=False,
            )

        await ctx.respond(embed=embed)


def setup(bot):
    bot.add_cog(Moderator(bot))
