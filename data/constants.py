from static.themes import default

# Embed colours
PRIMARY_CLR = 0x3FB09F
ERROR_CLR = 0xFF5858

# General settings
PERMISSONS = 412317248576
SUPPORT_SERVER_INVITE = "https://discord.gg/DHnk46C"

# Images
STATIC_IMAGE_FORMAT = "png"
GRAPH_CDN_BASE_URL = "https://image-cdn.thomascoin.repl.co"
GRAPH_EXPIRE_TIME = 60 * 60 * 24

PRIVACY_POLICY_LINK = "https://wordpracticebot.github.io/privacy-policy/"
RULES_LINK = "https://wordpracticebot.github.io/privacy-policy/rules"
GITHUB_LINK = "https://github.com/principle105"  # TODO: put the proper github link here

DEFAULT_VIEW_TIMEOUT = 45  # seconds
DEFAULT_THEME = default["Material"]["colours"]
AUTO_MODERATOR_NAME = "Thomas Worker 99"  # :)

AVG_AMT = 10

# Leaderboards
LB_LENGTH = 1000
LB_DISPLAY_AMT = 100

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
CAPTCHA_INTERVAL = 30  # tests
CAPTCHA_WPM_DEC = 0.15
CAPTCHA_ACC_PERC = 90
CAPTCHA_STARTING_THRESHOLD = 120
IMPOSSIBLE_THRESHOLD = 340
MAX_CAPTCHA_ATTEMPTS = 3

# Typing test image
FONT_SIZE = 21
TOP_BORDER = 5
SIDE_BORDER = 10
SPACING = 5
DEFAULT_WRAP = 45
MIN_PACER_SPEED = 50
PACER_PLANES = ["horizontal", "vertical"]

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
    "topgg-server": {
        "name": "Top.gg Server",
        "time": 12,  # hours,
        "link": "https://top.gg/servers/742960643312713738/vote",
    },
}

# Premium
PREMIUM_LAUNCHED = True
PREMIUM_LINK = "https://wordpractice.principle.sh/#/premium"

DONATION_LINK = "https://ko-fi.com/wordpractice"

# Score saving
SCORE_SAVE_AMT = 200
LIGHT_SAVE_AMT = 500
PREMIUM_SAVE_AMT = 1000
PREMIUM_PLUS_SAVE_AMT = 2500

# Daily challenges
CHALLENGE_AMT = 2
