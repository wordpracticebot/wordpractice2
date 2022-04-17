import discord
from discord.commands import Option
from discord.commands.permissions import CommandPermission
from discord.ext import commands

import icons
from config import MODERATORS, SUPPORT_GUILD_ID
from constants import SUPPORT_SERVER_INVITE
from helpers.checks import user_check
from helpers.converters import rqd_user
from helpers.ui import BaseView, create_link_view

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


class RestoreConfirm(BaseView):
    def __init__(self, ctx, user, backup):
        super().__init__(ctx)

        self.user = user
        self.backup = backup

    @discord.ui.button(label="Confirm Restore", style=discord.ButtonStyle.grey, row=1)
    async def confirm_restore(self, button, interaction):
        embed = self.ctx.default_embed(title="Restored user's accouunt")

        await interaction.message.edit(embed=embed, view=None)

        await self.ctx.bot.mongo.replace_user_data(self.user)

        await self.backup.delete()

    async def start(self):
        embed = self.ctx.default_embed(
            title="Restore Account",
            description=(
                "Are you sure you want to restore account?\n\n"
                f"All current data will be restored to data from <t:{self.backup.unix_wiped_at}:f>"
            ),
        )

        await self.ctx.respond(embed=embed, view=self)


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

        embed = ctx.default_embed(title="User Wiped")

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

        # Banning and wiping the user

        user_data = await self.bot.mongo.add_inf(
            ctx, user, user_data, ctx.author, reason, True
        )

        if wipe:
            await self.bot.mongo.wipe_user(user_data, ctx.author)
        else:
            await self.bot.mongo.replace_user_data(user_data)

        # Dming the user that they've been banned
        # Messaging is held off until the end because it is the least important

        embed = ctx.error_embed(
            title="You were banned",
            description=(
                f"Reason: {reason}\n\n"
                "Join the support server and create a ticket to request a ban appeal"
            ),
        )

        view = create_link_view({"Support Server": SUPPORT_SERVER_INVITE})

        try:
            await user.send(embed=embed, view=view)
        except Exception:
            pass

        embed = ctx.error_embed(
            title="User Banned",
            description=f"Reason: {reason}",
        )

        await ctx.respond(embed=embed)

    @mod_command
    async def unban(self, ctx, user: rqd_user(), reason):
        """Unban a user"""
        await ctx.defer()

        user_data = await self.handle_moderator_user(ctx, user)

        if user_data.banned is False:
            raise commands.BadArgument("That user is not banned")

        user_data = await self.bot.mongo.add_inf(
            ctx, user, user_data, ctx.author, reason, False
        )

        await self.bot.mongo.replace_user_data(user_data)

        embed = ctx.default_embed(title="User Unbanned")

        await ctx.respond(embed=embed)

    @mod_command
    async def cat(self, ctx, user: rqd_user()):
        """View the infractions of a user"""
        await ctx.defer()

        user_data = await self.handle_moderator_user(ctx, user)

        embed = ctx.error_embed(
            title=f"{user_data.username}'s Infractions",
            description=f"**Ban Status:** {user_data.banned}",
        )

        # TODO: add pagination

        for i, inf in enumerate(user_data.infractions):
            timestamp = inf.unix_timestamp

            embed.add_field(
                name=f"Infraction {i + 1} ({inf.name})",
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
        await ctx.defer()

        user_data = await self.handle_moderator_user(ctx, user)

        result = await self.bot.mongo.restore_user(user_data)

        if result is False:
            embed = ctx.error_embed(title=f"{icons.caution} User backup not found")

            return await ctx.respond(embed=embed)

        view = RestoreConfirm(ctx, *result)

        await view.start()


def setup(bot):
    bot.add_cog(Moderator(bot))
