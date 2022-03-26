from static.themes import default

# Embed colours
PRIMARY_CLR = 0x3FB09F
ERROR_CLR = 0xFF5858

# General settings
PERMISSONS = 412317248576
SUPPORT_SERVER_INVITE = "https://discord.gg/wordpractice"

# TODO: add the correct privacy policy and rule links
PRIVACY_POLICY_LINK = "https://www.google.com"
RULES_LINK = "https://www.google.com"

DEFAULT_VIEW_TIMEOUT = 25  # seconds
DEFAULT_THEME = default["Material"]["colours"]
AUTO_MODERATOR_NAME = "Thomas Worker 99"  # :)

SUPPORT_SERVER_ID = 903449744196661270

# Testing
DEBUG_GUILD = 903449744196661270

# Leaderboards
LB_LENGTH = 1000
LB_DISPLAY_AMT = 100
COMPILE_INTERVAL = 5  # minutes
UPDATE_24_HOUR_INTERVAL = 5  # minutes

# Achievements
BAR_SIZE = 10
ACHIEVEMENTS_SHOWN = 4

# Scores
SCORES_PER_PAGE = 5

# Typing test
MAX_RACE_JOIN = 10
RACE_JOIN_EXPIRE_TIME = 120  # seconds
TEST_EXPIRE_TIME = 180  # seconds
TEST_RANGE = (1, 100)
CAPTCHA_INTERVAL = 20  # tests

# Typing test image
FONT_SIZE = 21
TOP_BORDER = 4
SIDE_BORDER = 10
SPACING = 5
WRAP_WIDTH = 45

# Voting
VOTING_SITES = {
    "topgg": {
        "name": "Top.gg",
        "time": 12,  # hours
        "link": "https://top.gg/bot/743183681182498906/vote",
    },
    "dbls": {
        "name": "DBL",
        "time": 12,  # hours
        "link": "https://discordbotlist.com/bots/wordpractice/upvote",
    },
}

# Premium
PREMIUM_LAUNCHED = False
PREMIUM_LINK = "https://www.google.com"  # TODO: add the correct premium link

# Daily challenges
CHALLENGE_AMT = 2
