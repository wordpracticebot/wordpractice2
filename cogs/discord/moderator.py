import math

import discord
from discord.ext import bridge, commands

import icons
from config import MODERATORS, SUPPORT_GUILD_ID
from helpers.checks import user_check
from helpers.converters import user_option
from helpers.ui import BaseView, ScrollView, create_link_view
from helpers.utils import message_banned_user

INFRACTIONS_PER_PAGE = 3

BAN_AUTOCOMPLETE = [
    "Unfair Advantage",
    "Trading",
    "Advertisement",
    "Exploiting",
    "Breaking Discord TOS",
]


async def cog_check(ctx):
    return ctx.author.id in MODERATORS


mod_command = bridge.bridge_command(
    guild_ids=[SUPPORT_GUILD_ID],
    checks=[cog_check],
)


class CatView(ScrollView):
    def __init__(self, ctx, user):
        page_amt = math.ceil(len(user.infractions) / INFRACTIONS_PER_PAGE)

        super().__init__(ctx, page_amt)

        self.user = user

    async def create_page(self):
        total_infs = len(self.user.infractions)

        # TODO: add a util for this because it's duplicated in scoresview
        start_page = self.page * INFRACTIONS_PER_PAGE
        end_page = min((self.page + 1) * INFRACTIONS_PER_PAGE, total_infs)

        embed = self.ctx.error_embed(
            title=f"{self.user.username}'s Recent Infractions",
            description=f"**Current Ban Status:** {self.user.banned}",
        )

        for i, inf in enumerate(self.user.infractions[::-1][start_page:end_page]):
            timestamp = inf.unix_timestamp

            embed.add_field(
                name=f"Infraction {total_infs - (start_page + i)} ({inf.name})",
                value=(
                    f">>> Moderator: {inf.mod_name} ({inf.mod_id})\n"
                    f"Reason: {inf.reason}\n"
                    f"Timestamp: <t:{timestamp}:F>"
                ),
                inline=False,
            )

        return embed


class RestoreConfirm(BaseView):
    def __init__(self, ctx, user, backup):
        super().__init__(ctx)

        self.user = user
        self.backup = backup

    @discord.ui.button(label="Confirm Restore", style=discord.ButtonStyle.grey, row=1)
    async def confirm_restore(self, button, interaction):
        embed = self.ctx.default_embed(title="Restored user's account")

        await interaction.response.edit_message(embed=embed, view=None)

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

    hidden = True

    def __init__(self, bot):
        self.bot = bot

    async def handle_moderator_user(self, ctx, user):
        if user.id == ctx.author.id:
            raise commands.BadArgument("You cannot perform this action on yourself")

        return await user_check(ctx, user)

    @mod_command
    @user_option
    async def wipe(self, ctx, user: discord.User):
        """Wipe a user"""
        await ctx.defer()

        user_data = await self.handle_moderator_user(ctx, user)

        await self.bot.mongo.wipe_user(user_data, ctx.author)

        embed = ctx.default_embed(title=f"{user_data.username} was wiped!")

        await ctx.respond(embed=embed)

    @mod_command
    @user_option
    @discord.option(
        "reason",
        str,
        description="Reason for the ban",
        autocomplete=discord.utils.basic_autocomplete(BAN_AUTOCOMPLETE),
    )
    @discord.option(
        "wipe", bool, description="Whether the user's account should be wiped"
    )
    async def ban(self, ctx, user: discord.User, reason: str, wipe: bool):
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

        await message_banned_user(ctx, user, reason)

        embed = ctx.error_embed(
            title=f"{user_data.username} was banned!",
            description=f"Reason: {reason}",
        )

        await ctx.respond(embed=embed)

    @mod_command
    @user_option
    async def unban(self, ctx, user, reason):
        """Unban a user"""
        await ctx.defer()

        user_data = await self.handle_moderator_user(ctx, user)

        if user_data.banned is False:
            raise commands.BadArgument("That user is not banned")

        user_data = await self.bot.mongo.add_inf(
            ctx, user, user_data, ctx.author, reason, False
        )

        await self.bot.mongo.replace_user_data(user_data)

        embed = ctx.default_embed(title=f"{user_data.username} was unbanned!")

        await ctx.respond(embed=embed)

    @mod_command
    @user_option
    async def cat(self, ctx, user):
        """View the infractions of a user"""
        await ctx.defer()

        user_data = await self.handle_moderator_user(ctx, user)

        view = CatView(ctx, user_data)

        await view.start()

    @mod_command
    @user_option
    async def restore(self, ctx, user):
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
