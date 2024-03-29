from decouple import config

BOT_TOKEN = config("BOT_TOKEN")

# Database
DATABASE_URI = config("DATABASE_URI")
DATABASE_NAME = config("DATABASE_NAME")
REDIS_URL = config("REDIS_URL")

# Logging
COMMAND_LOG = config("COMMAND_LOG")
TEST_LOG = config("TEST_LOG")
IMPORTANT_LOG = config("IMPORTANT_LOG")
ERROR_LOG = config("ERROR_LOG")
GUILD_LOG = config("GUILD_LOG")

SUPPORT_GUILD_ID = config("SUPPORT_GUILD_ID", cast=int)
DEBUG_GUILD_ID = config("DEBUG_GUILD_ID", cast=int)

TESTING = config("TESTING", cast=bool, default=False)

DBL_TOKEN = config("DBL_TOKEN", default=None)
GRAPH_CDN_SECRET = config("GRAPH_CDN_SECRET")

MODERATORS = config(
    "MODERATORS", cast=lambda x: [int(m.strip()) for m in x.split(",")], default=[]
)
