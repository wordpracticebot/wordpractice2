import asyncio
from typing import TYPE_CHECKING

import discord
from discord.ext import bridge, commands

import data.icons as icons
from bot import Context, WordPractice
from config import MODERATORS, SUPPORT_GUILD_ID
from helpers.checks import user_check
from helpers.converters import discord_user_option
from helpers.ui import BaseView, ScrollView
from helpers.utils import message_banned_user

if TYPE_CHECKING:
    from cogs.utils.mongo import User

INFRACTIONS_PER_PAGE = 3

BAN_AUTOCOMPLETE = [
    "Unfair Advantage",
    "Trading",
    "Advertisement",
    "Exploiting",
    "Breaking Discord TOS",
]


async def cog_check(ctx: Context):
    return ctx.author.id in MODERATORS


mod_command = bridge.bridge_command(
    guild_ids=[SUPPORT_GUILD_ID],
    checks=[cog_check],
)


class CatView(ScrollView):
    def __init__(self, ctx: Context, user):
        super().__init__(ctx, iter=user.infractions, per_page=INFRACTIONS_PER_PAGE)

        self.user = user

    async def create_page(self):

        embed = self.ctx.error_embed(
            title=f"{self.user.username}'s Recent Infractions",
            description=f"**Current Ban Status:** {self.user.banned}",
        )

        for i, inf in enumerate(self.items):
            timestamp = inf.unix_timestamp

            embed.add_field(
                name=f"Infraction {self.total - (self.start_page + i)} ({inf.name})",
                value=(
                    f">>> Moderator: {inf.mod_name} ({inf.mod_id})\n"
                    f"Reason: {inf.reason}\n"
                    f"Timestamp: <t:{timestamp}:F>"
                ),
                inline=False,
            )

        return embed


class RestoreConfirm(BaseView):
    def __init__(self, ctx: Context, user: "User", backup):
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


class MessageModal(discord.ui.Modal):
    def __init__(self, ctx: Context) -> None:
        super().__init__(
            discord.ui.InputText(
                label="Send To",
                placeholder="Enter user IDs or mentions (separate with space)",
                style=discord.InputTextStyle.long,
            ),
            discord.ui.InputText(
                label="Title",
                placeholder="Enter a title",
            ),
            discord.ui.InputText(
                label="Description",
                placeholder="Enter a description",
                style=discord.InputTextStyle.long,
            ),
            discord.ui.InputText(
                label="Thumbnail",
                placeholder="Enter a thumbnail URL",
                required=False,
            ),
            title="Send a Message",
        )

        self.ctx = ctx

    async def callback(self, interaction: discord.Interaction):
        raw_send, title, desc, thumbnail = self.children

        embed = self.ctx.default_embed(title=title.value, description=desc.value)

        if thumbnail.value:
            embed.set_thumbnail(url=thumbnail.value)

        await interaction.response.send_message("Sending...")

        failed = []

        for u in raw_send.value.split("\n"):
            try:
                user = await self.ctx.bot.fetch_user(int(u))

                await user.send(embed=embed)

            except Exception:
                failed.append(u)

            else:
                # To prevent rate limiting
                await asyncio.sleep(3)

        failed_msg = "\n".join(failed)

        await self.ctx.send(
            f"Done!" + (f"\n\nFailed to send to: {failed_msg}" if failed_msg else "")
        )


class Moderator(commands.Cog):
    """Commands only for moderators..."""

    hidden = True

    def __init__(self, bot: WordPractice):
        self.bot = bot

    async def handle_moderator_user(self, ctx: Context, user):
        if user.id == ctx.author.id:
            raise commands.BadArgument("You cannot perform this action on yourself")

        return await user_check(ctx, user)

    @mod_command
    @discord_user_option
    async def wipe(self, ctx: Context, user: discord.User):
        """Wipe a user"""
        await ctx.defer()

        user_data = await self.handle_moderator_user(ctx, user)

        await self.bot.mongo.wipe_user(user_data, ctx.author)

        embed = ctx.default_embed(title=f"{user_data.username} was wiped!")

        await ctx.respond(embed=embed)

    @mod_command
    @discord_user_option
    @discord.option(
        "reason",
        str,
        description="Reason for the ban",
        autocomplete=discord.utils.basic_autocomplete(BAN_AUTOCOMPLETE),
    )
    @discord.option(
        "wipe", bool, description="Whether the user's account should be wiped"
    )
    async def ban(self, ctx: Context, user: discord.User, reason: str, wipe: bool):
        """Ban a user"""
        await ctx.defer()

        user_data = await self.handle_moderator_user(ctx, user)

        if user_data.banned:
            raise commands.BadArgument("That user is already banned")

        # Banning and wiping the user

        user_data = await self.bot.mongo.add_inf(
            ctx, user, user_data, reason, mod=ctx.author
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
    @discord_user_option
    async def unban(self, ctx: Context, user, reason):
        """Unban a user"""
        await ctx.defer()

        user_data = await self.handle_moderator_user(ctx, user)

        if user_data.banned is False:
            raise commands.BadArgument("That user is not banned")

        user_data = await self.bot.mongo.add_inf(
            ctx, user, user_data, reason, is_ban=False, mod=ctx.author
        )

        await self.bot.mongo.replace_user_data(user_data)

        embed = ctx.default_embed(title=f"{user_data.username} was unbanned!")

        await ctx.respond(embed=embed)

    @mod_command
    @discord_user_option
    async def cat(self, ctx: Context, user):
        """View the infractions of a user"""
        await ctx.defer()

        user_data = await self.handle_moderator_user(ctx, user)

        view = CatView(ctx, user_data)

        await view.start()

    @mod_command
    @discord_user_option
    async def restore(self, ctx: Context, user):
        """Restore a user's account"""
        await ctx.defer()

        user_data = await self.handle_moderator_user(ctx, user)

        result = await self.bot.mongo.restore_user(user_data)

        if result is False:
            embed = ctx.error_embed(title=f"{icons.caution} User backup not found")

            return await ctx.respond(embed=embed)

        view = RestoreConfirm(ctx, *result)

        await view.start()

    @mod_command
    async def status(self, ctx: Context, *, text: str):
        await self.bot.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching, name=f" {text}"
            )
        )

        embed = ctx.default_embed(title="Changed status")

        await ctx.respond(embed=embed)

    @mod_command
    async def message(self, ctx: Context):
        modal = MessageModal(ctx)

        await ctx.send_modal(modal)


def setup(bot: WordPractice):
    bot.add_cog(Moderator(bot))
