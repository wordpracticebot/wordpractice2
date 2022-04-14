import logging
import sys

from discord.ext import commands


class Logging(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        logging.getLogger("discord").setLevel(logging.INFO)

        self.log = logging.getLogger()
        self.log.setLevel(logging.INFO)

        handler = logging.StreamHandler(sys.stdout)

        fmt = logging.Formatter(
            "[{asctime}] [{levelname}] {name}: {message}",
            "%Y-%m-%d %H:%M:%S",
            style="{",
        )

        handler.setFormatter(fmt)

        self.log.addHandler(handler)


def setup(bot):
    bot.add_cog(Logging(bot))
