import discord
from discord.commands import Option, permissions
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

    async def handle_moderator_user(self, ctx, user):
        if user.id == ctx.author.id:
            raise commands.BadArgument("You cannot perform this action on yourself")

        return await user_check(ctx, user)

    # TODO: finish wipe command and allow for user to be wiped in ban command
    @commands.slash_command(guild_ids=[SUPPORT_SERVER_ID], default_permission=False)
    @permissions.is_owner()
    @commands.is_owner()
    async def wipe(self, ctx, user: rqd_user()):
        """Wipe a user"""
        user_data = await self.handle_moderator_user(ctx, user)

        await self.bot.mongo.wipe_user(user_data, ctx.author)

        embed = ctx.embed(title="User Wiped", add_footer=False)

        await ctx.respond(embed=embed)

    # TODO: only enable for users who are moderators
    @commands.slash_command(guild_ids=[SUPPORT_SERVER_ID], default_permission=False)
    @permissions.is_owner()
    @commands.is_owner()
    async def ban(
        self,
        ctx,
        user: rqd_user(),
        reason: Option(
            str,
            "Reason for the ban",
            autocomplete=discord.utils.basic_autocomplete(BAN_AUTOCOMPLETE),
        ),
        wipe: Option(bool, "Whether the user's account should be wiped"),
    ):
        """Ban a user"""
        user_data = await self.handle_moderator_user(ctx, user)

        if user_data.banned:
            raise commands.BadArgument("That user is already banned")

        await self.bot.mongo.ban_user(user, reason, ctx.author)

        if wipe:
            await self.bot.mongo.wipe_user(user_data, ctx.author)

        embed = ctx.error_embed(
            title="User Banned",
            description=f"Reason: {reason}",
        )

        await ctx.respond(embed=embed)

    @commands.slash_command(guild_ids=[SUPPORT_SERVER_ID], default_permission=False)
    @permissions.is_owner()
    @commands.is_owner()
    async def unban(self, ctx, user: rqd_user()):
        """Unban a user"""
        user_data = await self.handle_moderator_user(ctx, user)

        if user_data.banned is False:
            raise commands.BadArgument("That user is not banned")

        user_data.banned = False

        await self.bot.mongo.replace_user_data(user_data)

        embed = ctx.default_embed(title="User Unbanned")

        await ctx.respond(embed=embed)

    @commands.slash_command(guild_ids=[SUPPORT_SERVER_ID], default_permission=False)
    @permissions.is_owner()
    @commands.is_owner()
    async def cat(self, ctx, user: rqd_user()):
        """View the infractions of a user"""

        user_data = await self.handle_moderator_user(ctx, user)

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
