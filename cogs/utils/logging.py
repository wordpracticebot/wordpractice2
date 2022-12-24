import logging
import sys

from discord.ext import commands

from bot import WordPractice


class Logging(commands.Cog):
    def __init__(self, bot: WordPractice):
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


def setup(bot: WordPractice):
    bot.add_cog(Logging(bot))
