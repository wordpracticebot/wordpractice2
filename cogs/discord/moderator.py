import discord
from discord.commands import Option
from discord.commands.permissions import CommandPermission
from discord.ext import commands

from config import MODERATORS, SUPPORT_GUILD_ID
from helpers.checks import user_check
from helpers.converters import rqd_user

BAN_AUTOCOMPLETE = [
    "Cheating",
    "Trading",
    "Advertisement",
    "Exploiting",
    "Breaking Discord TOS",
]

mod_command = commands.slash_command(
    guild_ids=[SUPPORT_GUILD_ID],
    default_permission=False,
    permissions=[
        CommandPermission(id=user_id, type=2, permission=True) for user_id in MODERATORS
    ],
)


class Moderator(commands.Cog):
    """Commands only for moderators..."""

    def __init__(self, bot):
        self.bot = bot

    async def handle_moderator_user(self, ctx, user):
        if user.id == ctx.author.id:
            raise commands.BadArgument("You cannot perform this action on yourself")

        return await user_check(ctx, user)

    @mod_command
    async def wipe(self, ctx, user: rqd_user()):
        """Wipe a user"""
        await ctx.defer()

        user_data = await self.handle_moderator_user(ctx, user)

        await self.bot.mongo.wipe_user(user_data, ctx.author)

        embed = ctx.embed(title="User Wiped", add_footer=False)

        await ctx.respond(embed=embed)

    @mod_command
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
        await ctx.defer()

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

    @mod_command
    async def unban(
        self,
        ctx,
        user: rqd_user(),
        restore: Option(bool, "Whether the user's account should be restored"),
    ):
        """Unban a user"""
        user_data = await self.handle_moderator_user(ctx, user)

        if user_data.banned is False:
            raise commands.BadArgument("That user is not banned")

        user_data.banned = False

        await self.bot.mongo.replace_user_data(user_data)

        embed = ctx.default_embed(title="User Unbanned")

        await ctx.respond(embed=embed)

    @mod_command
    async def cat(self, ctx, user: rqd_user()):
        """View the infractions of a user"""

        user_data = await self.handle_moderator_user(ctx, user)

        embed = ctx.error_embed(
            title=f"{user_data.username}'s Infractions",
            description=f"**Ban Status:** {user_data.banned}",
        )

        # TODO: add pagination

        for i, inf in enumerate(user_data.infractions):
            timestamp = inf.unix_timestamp

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

    @mod_command
    async def restore(self, ctx, user: rqd_user()):
        """Restore a user's account"""

        user_data = await self.handle_moderator_user(ctx, user)


def setup(bot):
    bot.add_cog(Moderator(bot))
