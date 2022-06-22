import discord

from bot import WordPractice
from config import DEBUG_GUILD_ID


def main():
    intents = discord.Intents.none()

    # Privileged intents
    intents.message_content = True
    intents.messages = True
    intents.guilds = True

    allowed_mentions = discord.AllowedMentions(everyone=False, roles=False)

    # Creating an instance of the bot client
    bot = WordPractice(
        command_prefix="%",
        allowed_mentions=allowed_mentions,
        chunk_guilds_at_startup=False,
        help_command=None,
        debug_guild=DEBUG_GUILD_ID,
        intents=intents,
    )

    bot.run()


if __name__ == "__main__":
    main()
