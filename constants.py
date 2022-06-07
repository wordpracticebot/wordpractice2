from static.themes import default

# Embed colours
PRIMARY_CLR = 0x3FB09F
ERROR_CLR = 0xFF5858

# General settings
PERMISSONS = 412317248576
SUPPORT_SERVER_INVITE = "https://discord.gg/wordpractice"

# Images
STATIC_IMAGE_FORMAT = "png"
GRAPH_CDN_BASE_URL = "https://image-cdn.thomascoin.repl.co"
GRAPH_EXPIRE_TIME = 60 * 60 * 24

PRIVACY_POLICY_LINK = "https://wordpracticebot.github.io/privacy-policy/"
RULES_LINK = "https://wordpracticebot.github.io/privacy-policy/rules"
INFO_VIDEO = "https://www.youtube.com/"
GITHUB_LINK = "https://github.com/principle105"  # TODO: put the proper github link here

DEFAULT_VIEW_TIMEOUT = 30  # seconds
DEFAULT_THEME = default["Material"]["colours"]
AUTO_MODERATOR_NAME = "Thomas Worker 99"  # :)

# Leaderboards
LB_LENGTH = 1000
LB_DISPLAY_AMT = 100
COMPILE_INTERVAL = 5  # minutes
UPDATE_24_HOUR_INTERVAL = 10  # minutes

# Achievements
ACHIEVEMENTS_SHOWN = 4

# Typing test
MAX_RACE_JOIN = 10
RACE_JOIN_EXPIRE_TIME = 120  # seconds
TEST_EXPIRE_TIME = 180  # seconds
TEST_RANGE = (1, 100)
TEST_ZONES = {"short": range(10, 21), "medium": range(21, 51), "long": range(51, 101)}
TEST_LOAD_TIME = 5

# Typing test anti cheat
SUSPICIOUS_THRESHOLD = 180
CAPTCHA_INTERVAL = 20  # tests
CAPTCHA_WPM_DEC = 0.15
CAPTCHA_ACC_PERC = 90
CAPTCHA_STARTING_THRESHOLD = 120
IMPOSSIBLE_THRESHOLD = 300
MAX_CAPTCHA_ATTEMPTS = 2

# Typing test image
FONT_SIZE = 21
TOP_BORDER = 5
SIDE_BORDER = 10
SPACING = 5
DEFAULT_WRAP = 45
MIN_PACER_SPEED = 50

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

PREMIUM_SCORE_LIMIT = 250
REGULAR_SCORE_LIMIT = 50

# Daily challenges
CHALLENGE_AMT = 2
