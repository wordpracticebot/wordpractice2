import logging
import sys

from discord.ext import commands

from config import TESTING


class Logging(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        logging.getLogger("discord").setLevel(logging.INFO)

        self.log = logging.getLogger()
        self.log.setLevel(logging.INFO)

        prod_or_dev = "DEV" if TESTING else "PROD"

        handler = logging.StreamHandler(sys.stdout)

        fmt = logging.Formatter(
            f"[{prod_or_dev}] " + "[{asctime}] [{levelname}] {name}: {message}",
            "%Y-%m-%d %H:%M:%S",
            style="{",
        )
        handler.setFormatter(fmt)
        self.log.addHandler(handler)


def setup(bot):
    bot.add_cog(Logging(bot))
