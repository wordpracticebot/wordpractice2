from static.themes import default

# Embed colours
PRIMARY_CLR = 0x3FB09F
ERROR_CLR = 0xFF5858

# General settings
PERMISSONS = 412317248576
SUPPORT_SERVER = "https://discord.gg/wordpractice"
PRIVACY_POLICY = ""
UPDATE_24_HOUR = 5  # minutes
DEFAULT_THEME = default["Discord Dark Theme"]["colours"]

# Testing
DEBUG_GUILD = 903449744196661270

# Leaderboards
LB_LENGTH = 500
COMPILE_INTERVAL = 5  # minutes
UPDATE_24_HOUR_INTERVAL = 5  # minutes

# Achievements
BAR_SIZE = 10
ACHIEVEMENTS_SHOWN = 4

# Typing test
MAX_RACE_JOIN = 10
TEST_RANGE = (1, 100)

# Voting
VOTING_SITES = {
    "Top.gg": {
        "time": 12,  # hours
        "link": "https://top.gg/bot/743183681182498906/vote",
    },
    "DBL": {
        "time": 12,  # hours
        "link": "https://discordbotlist.com/bots/wordpractice/upvote",
    },
}

# Premium
PREMIUM_LAUNCHED = True
PREMIUM_LINK = "https://www.google.com"  # TODO: add the correct premium link
