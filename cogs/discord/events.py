import time
import discord
import traceback
import constants
from io import BytesIO
from discord.ext import commands
from discord.ext.commands import errors
from helpers.ui import create_link_view


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @staticmethod
    async def send_error(ctx, title, desc, view=None):
        embed = ctx.bot.error_embed(title=title, description=desc)
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
        pass

    async def handle_check_failure(self, ctx, error):
        pass

    async def handle_unexpected_error(self, ctx, error):
        view = create_link_view({"Support Server": constants.SUPPORT_SERVER})
        await self.send_error(
            ctx,
            "Unexpected Error",
            (
                f"Report this using `{ctx.prefix}report [message]`\n"
                "or join our support server."
            ),
            view,
        )

        timestamp = int(time.time())

        embed = self.bot.error_embed(
            title="Unexpected Error",
            description=(
                f"**User:** {ctx.author} ({ctx.author.id})\n"
                f"**Server:** {ctx.guild} ({ctx.guild.id})\n"
                f"**Message:** {ctx.message.content}\n"
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
        await self.bot.log_interaction(ctx)


def setup(bot):
    bot.add_cog(Events(bot))
