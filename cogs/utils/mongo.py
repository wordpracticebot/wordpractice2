import pickle
import time
from datetime import datetime
from typing import Union

import discord
import pymongo
from discord.ext import commands
from discord.utils import escape_markdown
from motor.motor_asyncio import AsyncIOMotorClient
from umongo import Document, EmbeddedDocument
from umongo.fields import (
    BooleanField,
    DateTimeField,
    DictField,
    EmbeddedField,
    FloatField,
    IntegerField,
    ListField,
    StringField,
)
from umongo.frameworks import MotorAsyncIOInstance

from config import DATABASE_NAME, DATABASE_URI
from constants import (
    AUTO_MODERATOR_NAME,
    DEFAULT_THEME,
    PREMIUM_LAUNCHED,
    TEST_ZONES,
    VOTING_SITES,
)
from helpers.ui import get_log_embed
from helpers.user import get_expanded_24_hour_stat
from helpers.utils import datetime_to_unix
from static.badges import get_badge_from_id, get_badges_from_ids


def get_meta_data(user):
    return {
        "id": user.id,
        "name": user.name,
        "discriminator": user.discriminator,
        "avatar": user.avatar,
        "created_at": user.created_at,
        "infractions": user.infractions,
        "banned": user.banned,
    }


class Infraction(EmbeddedDocument):
    mod_name = StringField(required=True)  # NAME#DISCRIMINATOR
    mod_id = IntegerField(require=True)

    is_ban = BooleanField(required=True)  # True = ban, False = unban

    reason = StringField(required=True)

    timestamp = DateTimeField(required=True)

    @property
    def unix_timestamp(self):
        return datetime_to_unix(self.timestamp)

    @property
    def name(self):
        return "Ban" if self.is_ban else "Unban"


class Score(EmbeddedDocument):
    wpm = FloatField(default=0.0)
    raw = FloatField(default=0.0)
    acc = FloatField(default=0.0)

    # correct words
    cw = IntegerField(default=0)
    # total words
    tw = IntegerField(default=0)

    xp = IntegerField(default=0)
    timestamp = DateTimeField(default=datetime.min)

    @property
    def unix_timestamp(self):
        return datetime_to_unix(self.timestamp)


class UserBase(Document):
    class Meta:
        abstract = True

    # General member information
    id = IntegerField(attribute="_id")
    name = StringField(required=True)
    discriminator = IntegerField(required=True)
    avatar = StringField(default=None)
    created_at = DateTimeField(required=True)
    premium = BooleanField(default=False)

    # list of commands that the user has run before (for context tutorials)
    # includes subcommands from groups
    cmds_run = ListField(StringField, default=[])

    # Statistics
    words = IntegerField(default=0)

    # Season
    xp = IntegerField(default=0)

    # Daily challenge
    is_daily_complete = BooleanField(default=False)

    # 24 Hour
    last24 = ListField(ListField(IntegerField), default=[[0], [0]])  # words, xp
    best24 = EmbeddedField(Score, default=None)  # best score in the last 24 hours

    # Daily
    test_amt = IntegerField(default=0)  # amount of tests in the last day

    # Typing
    highspeed = DictField(StringField(), EmbeddedField(Score), required=True)
    scores = ListField(EmbeddedField(Score), default=[])

    # Other statistics
    achievements = DictField(
        StringField(), ListField(DateTimeField), default=[]
    )  # id: timestamp
    trophies = ListField(
        IntegerField, default=[0, 0, 0, 0]
    )  # [first, second, third, top 10]

    # Cosmetics
    badges = ListField(StringField, default=[])
    status = StringField(default="")

    # Streak of playing
    streak = IntegerField(default=0)  # days
    highest_streak = IntegerField(default=0)
    last_streak = DateTimeField(required=True)  # not last bot usage time

    # Voting
    votes = IntegerField(default=0)

    last_voted = DictField(
        StringField(),
        DateTimeField(),
        default={name: datetime.min for name in VOTING_SITES.keys()},
    )

    # Infractions
    infractions = ListField(EmbeddedField(Infraction), default=[])
    banned = BooleanField(default=False)

    # Settings
    theme = ListField(StringField, default=DEFAULT_THEME)
    language = StringField(default="english")
    level = StringField(default="easy")
    pacer_speed = StringField(default="")  # "", "avg", "pb", "INTEGER"
    pacer_type = IntegerField(default=0)  # 0 = horizontal, 1 = vertical


class User(UserBase):
    class Meta:
        collection_name = "users"

    @property
    def status_emoji(self):
        return get_badge_from_id(self.status) or ""

    @property
    def badges_emojis(self):
        return get_badges_from_ids(self.badges)

    @property
    def avatar_url(self):
        return f"https://cdn.discordapp.com/avatars/{self.id}/{self.avatar}"

    @property
    def username(self):
        return escape_markdown(f"{self.name}#{self.discriminator}")

    @property
    def display_name(self):
        return self.username + (f" {self.status_emoji}" if self.status else "")

    @property
    def is_premium(self):
        return not PREMIUM_LAUNCHED or self.premium

    @property
    def highest_speed(self):
        return max(s.wpm for s in self.highspeed.values())

    def add_words(self, words: int):
        self.words += words

        if words != 0:
            current = get_expanded_24_hour_stat(self.last24[0])
            current[-1] += words

            self.last24[0] = current

    def add_xp(self, xp: int):
        self.xp += xp

        if xp != 0:
            current = get_expanded_24_hour_stat(self.last24[1])
            current[-1] += xp

            self.last24[1] = current

    def add_score(self, score: Score):
        limit = 200 if self.is_premium else 50

        if len(self.scores) >= limit:
            del self.scores[: len(self.scores) - limit + 1]

        self.scores.append(score)

        if self.best24 is None or score.wpm > self.best24.wpm:
            self.best24 = score


# Backup for users that have been wiped
# TODO: add a timestamp and remove backups after 60 days
class UserBackup(UserBase):
    wiped_at = DateTimeField(required=True)

    class Meta:
        collection_name = "backup"

    @property
    def unix_wiped_at(self):
        return datetime_to_unix(self.wiped_at)


class Mongo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = AsyncIOMotorClient(DATABASE_URI, io_loop=bot.loop)[DATABASE_NAME]

        instance = MotorAsyncIOInstance(self.db)

        g = globals()

        for n in ("Infraction", "Score", "UserBase", "User", "UserBackup"):
            setattr(self, n, instance.register(g[n]))
            getattr(self, n).bot = bot

    def get_auto_mod(self, mod):
        if mod is None:
            mod = AUTO_MODERATOR_NAME
            mod_id = self.bot.user.id
        else:
            mod_id = mod.id
            mod = str(mod)

        return mod, mod_id

    def get_user_from_cache(self, user_id: int):
        u = self.bot.user_cache.get(user_id)

        if u is not None:
            u = self.User.build_from_mongo(pickle.loads(u))

        return u

    @property
    def default_score(self):
        # Schemas are instantiated when mongo cog is initialized
        # Default scores must be passed in at initialization to access schema
        score = dict(self.Score.schema.as_marshmallow_schema()().load({}))

        return {s: score for s in TEST_ZONES.keys()}

    async def fetch_user(self, user: Union[discord.Member, int], create=False):
        if isinstance(user, int):
            user_id = user
        else:
            user_id = user.id

        # Checking if the user is in the cache
        u = self.get_user_from_cache(user_id)

        if u is None:
            u = await self.User.find_one({"id": user_id})

            if u is None:
                if not isinstance(user, int) and not user.bot:
                    if create is False:
                        return u

                    u = self.User(
                        id=user.id,
                        name=user.name,
                        discriminator=user.discriminator,
                        avatar=user.avatar.key if user.avatar else None,
                        highspeed=self.default_score,
                        created_at=datetime.utcnow(),
                        last_streak=datetime.utcnow(),
                    )

                    await self.replace_user_data(u)
                else:
                    self.bot.user_cache[user_id] = None
                    return None

                return u

        uj = u.to_mongo()

        if not isinstance(user, int):
            current = self.get_current(user)

            # Checking if user info needs to be updated
            if current.values() != [u.name, u.discriminator, u.avatar]:
                await self.update_user(user.id, {"$set": current})
                uj.update(current)

            u = self.User.build_from_mongo(uj)

        # Updating in cache
        self.bot.user_cache[user_id] = pickle.dumps(uj)

        return u

    def get_current(self, user):
        return {
            "name": user.name,
            "discriminator": user.discriminator,
            "avatar": user.avatar.key if user.avatar else None,
        }

    async def wipe_user(self, user, mod: Union[discord.Member, discord.User] = None):
        mod, mod_id = self.get_auto_mod(mod)

        timestamp = round(time.time())

        embed = self.bot.error_embed(
            title="Account Wiped",
            description=(
                f"**User:** {user.username} ({user.id})\n"
                f"**Moderator:** {mod} ({mod_id})\n"
                f"**Timestamp:** <t:{timestamp}:R>"
            ),
        )
        await self.bot.impt_wh.send(embed=embed)

        # Saving a backup in the database

        backup = await self.UserBackup.find_one({"id": user.id})

        # TODO: max it replace the data instead of deleting
        if backup is not None:
            await backup.delete()

        # Building object from_mongo does not work when trying to commit
        backup = self.UserBackup(**user.dump(), wiped_at=datetime.utcnow())

        try:
            await backup.commit()
        except pymongo.errors.DuplicateKeyError:
            pass

        # Resetting the user's data

        meta_data = get_meta_data(user)

        # Resetting the user's account
        new_data = self.User(
            **meta_data,
            last_streak=datetime.utcnow(),
            highspeed=self.default_score,
        )

        for field, value in new_data.dump().items():
            if field not in meta_data:
                user[field] = value

        await self.replace_user_data(user)

    async def restore_user(self, user):
        backup = await self.UserBackup.find_one({"id": user.id})

        if backup is None:
            return False

        meta_data = get_meta_data(user)

        backup_data = backup.dump()
        del backup_data["wiped_at"]

        for field, value in backup_data.items():
            if field not in meta_data:
                user[field] = value

        return user, backup

    async def update_user(self, user, query: dict):
        if isinstance(user, int):
            user_id = user
        else:
            user_id = user.id

        # Updating user data
        if not isinstance(user, int):
            current = self.get_current(user)

            if "$set" in query:
                query["$set"].update(current)

        await self.db.users.update_one({"_id": user_id}, query)

        if user_id in self.bot.user_cache:
            del self.bot.user_cache[user_id]

    async def replace_user_data(self, new_user, member=None):
        if member is not None:
            current = self.get_current(member)

            new_user.update(current)

        try:
            await new_user.commit()
        except pymongo.errors.DuplicateKeyError:
            pass
        else:
            # Caching new user data
            self.bot.user_cache[new_user.id] = pickle.dumps(new_user.to_mongo())

    async def add_inf(self, ctx, user, user_data, mod, reason, is_ban: bool):
        """Doesn't update in the database"""

        mod, mod_id = self.get_auto_mod(mod)

        inf = self.Infraction(
            mod_name=mod,
            mod_id=mod_id,
            is_ban=is_ban,
            reason=reason,
            timestamp=datetime.utcnow(),
        )

        user_data.infractions.append(inf)
        user_data.banned = is_ban

        # Logging the infraction
        embed = get_log_embed(
            ctx,
            title=f"User {inf.name}ned",  # sorry
            additional=f"**Moderator:** {mod} ({mod_id})\n**Reason:** {reason}",
            error=True,
            author=user,
        )

        await self.bot.impt_wh.send(embed=embed)

        return user_data


def setup(bot):
    bot.add_cog(Mongo(bot))
