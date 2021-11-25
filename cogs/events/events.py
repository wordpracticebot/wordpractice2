import time
from discord.ext import commands
from discord.ext.commands import errors
from rapidfuzz import fuzz, process
from rapidfuzz.utils import default_process
from helpers.utils import filter_commands


def get_similar_results(name, choices):
    print(name, choices)
    result = process.extract(
        default_process(name),
        choices,
        scorer=fuzz.ratio,
        score_cutoff=60,
        processor=None,
    )

    return [match[0] for match in result[:3]]


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # TODO: use dispatch

    # Processing edited messages
    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if after.content != before.content:
            await self.bot.process_commands(after)

    @commands.Cog.listener()
    async def on_command(self, ctx):
        timestamp = int(time.time())

        embed = self.embed(
            description=(
                f"**Username:** {ctx.author}\n"
                f"**User ID:** {ctx.author.id}\n"
                f"**Command:** {ctx.command.name}\n"
                f"**Message:** {ctx.message.content}\n"
                f"**Server:** {ctx.guild}\n"
                f"**Server ID:** {ctx.guild.id}\n"
                f"UTC Timestamp: <t:{timestamp}:R>"
            )
        )

        await self.bot.cmd_wh.send(embed=embed)

    @staticmethod
    async def send_error(ctx, title, desc):
        embed = ctx.bot.error_embed(title=title, description=desc)
        await ctx.reply(embed=embed)

    @staticmethod
    async def get_options(ctx):
        options = set()
        for cmd in await filter_commands(ctx, ctx.bot.walk_commands()):
            options.add(str(cmd))

            if isinstance(cmd, commands.Command):
                options.update(cmd.aliases)

        return list(options)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error: errors.CommandError):
        if isinstance(error, errors.CommandNotFound):

            matches = get_similar_results(
                ctx.message.content[:25],  # to prevent spam
                await self.get_options(ctx),
            )

            matches = "\n".join(f"`{m}`" for m in matches) if matches != [] else ""

            await self.send_error(
                ctx,
                "Command Not Found",
                (
                    f"Type `{ctx.prefix}help` for a list of commands\n\n"
                    f"**Did you mean**\n{matches}"
                ),
            )

        elif isinstance(error, errors.UserInputError):
            await self.handle_input_error(ctx, error)

        elif isinstance(error, errors.CheckFailure):
            await self.handle_check_error(ctx, error)

        elif isinstance(error, errors.DisabledCommand):
            await self.send_error(
                ctx, "Command Disabled", "Try running this command another time"
            )

        elif isinstance(error, errors.MaxConcurrencyReached):
            return

        else:
            await self.handle_unexpected_error(ctx, error)

        # TODO: finish conversion errors
        # errors.ConversionError

    async def handle_input_error(self, ctx, error: errors.UserInputError):
        if isinstance(error, errors.MissingRequiredArgument):
            await self.send_error(
                ctx,
                "Missing Required Argument",
                (
                    f"You are missing the required argument `{error.param.name}`\n\n"
                    f"**Command Usage:** `{ctx.prefix}{ctx.command} {ctx.command.signature}`"
                ),
            )
        elif isinstance(error, errors.MissingRequiredArgument):
            await self.send_error(ctx, "Too Many Arguments", str(error))
        elif isinstance(error, errors.BadArgument):
            await self.send_error(ctx, "Invalid Argument", str(error))

        else:
            await self.send_error(
                ctx,
                "Invalid Input",
                (
                    "Your input is malformed"
                    f"Type `{ctx.prefix}help` for a list of commands"
                ),
            )

    async def handle_check_error(self, ctx, error: errors.CheckFailure):
        if isinstance(
            error,
            (
                errors.BotMissingPermissions,
                errors.BotMissingRole,
                errors.BotMissingAnyRole,
            ),
        ):
            await self.send_error(
                ctx, "Permission Error", "I am missing the correct server permissions"
            )

    async def handle_unexpected_error(self, ctx, error: errors.CommandError):
        # TODO: finish unexpected errors
        pass


def setup(bot):
    bot.add_cog(Events(bot))
