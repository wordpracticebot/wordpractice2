import time
import discord
import traceback
import constants
from io import BytesIO
from discord.ext import commands
from discord.ext.commands import errors
from helpers.ui import create_link_view
from helpers.errors import ImproperArgument


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def log_interaction(self, ctx):
        # Logging the interaction

        timestamp = int(time.time())

        options = (
            " ".join(f"[{o.name}]" for o in ctx.command.options)
            if ctx.command.options
            else ""
        )

        embed = self.bot.embed(
            description=(
                f"**User:** {ctx.author} ({ctx.author.id})\n"
                f"**Server:** {ctx.guild} ({ctx.guild.id})\n"
                f"**Command:** {ctx.command.name} {options}\n"
                f"**Timestamp:** <t:{timestamp}:R>"
            ),
            add_footer=False,
        )

        await self.bot.cmd_wh.send(embed=embed)

    @staticmethod
    async def send_error(ctx, title, desc, view=None):
        embed = ctx.bot.error_embed(title=title, description=desc)

        if view is None:
            await ctx.respond(embed=embed)
        else:
            await ctx.respond(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_application_command_error(self, ctx, error):
        error = error.original

        if isinstance(error, errors.UserInputError):
            await self.handle_user_input_error(ctx, error)

        elif isinstance(error, errors.CheckFailure):
            await self.handle_check_failure(ctx, error)

        elif isinstance(error, errors.MaxConcurrencyReached):
            return

        else:
            await self.handle_unexpected_error(ctx, error)

    async def handle_user_input_error(self, ctx, error):
        if isinstance(error, errors.BadArgument):
            message = str(error)

            if isinstance(error, ImproperArgument) and error.options:
                options = " ".join(f"`{o}`" for o in error.options)
                message += f"\n\n**Did you mean?**\n{options}"

            await self.send_error(ctx, "Invalid Argument", message)
        
        else:
            await self.send_error(
                ctx,
                "Invalid Input",
                (
                    "Your input is malformed"
                    f"Type `{ctx.prefix}help` for a list of commands"
                ),
            )


    async def handle_check_failure(self, ctx, error):
        if isinstance(
            error,
            (
                errors.BotMissingPermissions,
                errors.BotMissingRole,
                errors.BotMissingAnyRole,
            ),
        ):
            try:
                await self.send_error(
                    ctx, "Permission Error", "I do not have the correct server permissons"
                )
            except: # base exception :eyes:
                pass


    async def handle_unexpected_error(self, ctx, error):
        view = create_link_view({"Support Server": constants.SUPPORT_SERVER})

        await self.send_error(
            ctx,
            "Unexpected Error",
            "Please report this through our support server so we can fix it.",
            view,
        )

        timestamp = int(time.time())

        options = (
            " ".join(f"[{o.name}]" for o in ctx.command.options)
            if ctx.command.options
            else ""
        )

        embed = self.bot.error_embed(
            title="Unexpected Error",
            description=(
                f"**User:** {ctx.author} ({ctx.author.id})\n"
                f"**Server:** {ctx.guild} ({ctx.guild.id})\n"
                f"**Command:** {ctx.command.name} {options}\n"
                f"**Timestamp:** <t:{timestamp}:R>"
            ),
            add_footer=False,
        )

        msg = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )

        buffer = BytesIO(msg.encode("utf-8"))
        file = discord.File(buffer, filename="text.txt")

        await self.bot.impt_wh.send(embed=embed, file=file)

    @commands.Cog.listener()
    async def on_application_command(self, ctx):
        await self.log_interaction(ctx)


def setup(bot):
    bot.add_cog(Events(bot))
