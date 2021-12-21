import traceback
from discord.ext import commands
from discord.ext.commands import errors


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    #
    @commands.Cog.listener()
    async def on_application_command_error(self, ctx, error):
        error = error.original

        if isinstance(error, errors.UserInputError):
            print("user input error")

        elif isinstance(error, errors.CheckFailure):
            print("Check failure")

        elif isinstance(error, errors.MaxConcurrencyReached):
            print("max concurrency")
            return

        else:
            msg = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )
            print("unexpected", msg)

    @commands.Cog.listener()
    async def on_application_command(self, ctx):
        await self.bot.log_interaction(ctx)


def setup(bot):
    bot.add_cog(Events(bot))
