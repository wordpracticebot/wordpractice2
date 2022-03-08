try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

import os
from collections import namedtuple

import discord

from bot import WordPractice
from constants import DEBUG_GUILD

Config = namedtuple(
    "Config",
    [
        "BOT_TOKEN",
        "DATABASE_URI",
        "DATABASE_NAME",
        "DBL_TOKEN",
        "COMMAND_LOG",
        "TEST_LOG",
        "IMPORTANT_LOG",
        "ERROR_LOG",
    ],
)


def main():
    # Creating the config object
    config = Config(
        BOT_TOKEN=os.environ["BOT_TOKEN"],
        DATABASE_URI=os.environ["DATABASE_URI"],
        DATABASE_NAME=os.environ["DATABASE_NAME"],
        DBL_TOKEN=os.environ["DBL_TOKEN"],
        COMMAND_LOG=os.environ["COMMAND_LOG"],
        TEST_LOG=os.environ["TEST_LOG"],
        IMPORTANT_LOG=os.environ["IMPORTANT_LOG"],
        ERROR_LOG=os.environ["ERROR_LOG"],
    )

    intents = discord.Intents.default()

    # Privileged intents
    intents.members = True
    intents.message_content = True

    allowed_mentions = discord.AllowedMentions(everyone=False, roles=False)

    # Creating an instance of the bot client
    bot = WordPractice(
        config=config,
        allowed_mentions=allowed_mentions,
        chunk_guilds_at_startup=False,
        debug_guild=DEBUG_GUILD,
        intents=intents,
    )

    bot.run()


if __name__ == "__main__":
    main()
