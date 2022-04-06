import discord

from bot import WordPractice
from config import DEBUG_GUILD_ID


def main():
    intents = discord.Intents.default()

    # Privileged intents
    intents.members = True
    intents.message_content = True

    allowed_mentions = discord.AllowedMentions(everyone=False, roles=False)

    # Creating an instance of the bot client
    bot = WordPractice(
        allowed_mentions=allowed_mentions,
        chunk_guilds_at_startup=False,
        debug_guild=DEBUG_GUILD_ID,
        intents=intents,
    )

    bot.run()


if __name__ == "__main__":
    main()
