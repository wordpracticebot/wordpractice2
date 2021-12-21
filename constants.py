import os

# Embed colours
PRIMARY_CLR = 0x3FB09F
ERROR_CLR = 0xFF5858

# General settings
SUPPORT_SERVER = "https://discord.gg/wordpractice"

# Whether the bot is in a testing environment
GUILDS = None if (b := os.environ.get("GUILDS")) is None else [int(b)]
