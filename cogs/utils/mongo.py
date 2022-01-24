import pickle
import time
from datetime import datetime
from typing import Union

import discord
import pymongo
from discord.ext import commands
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

from constants import VOTING_SITES, DEFAULT_THEME


class Infraction(EmbeddedDocument):
    moderator = StringField(required=True)  # NAME#DISCRIMINATOR (ID)
    reason = StringField(required=True)
    timestamp = DateTimeField(required=True)


class Score(EmbeddedDocument):
    wpm = FloatField(required=True)
    raw = FloatField(required=True)
    acc = FloatField(required=True)

    # correct words
    cw = IntegerField(required=True)
    # total words
    tw = IntegerField(required=True)

    # User input
    u_input = StringField(required=True)

    # Quote
    quote = ListField(StringField, required=True)

    # xp earnings
    earnings = IntegerField(required=True)
    timestamp = DateTimeField(required=True)


class User(Document):
    # General member information
    id = IntegerField(attribute="_id")
    name = StringField(required=True)
    discriminator = IntegerField(required=True)
    avatar = StringField(default=None)
    created_at = DateTimeField(default=datetime.now())

    # Statistics
    words = IntegerField(default=0)
    last24 = ListField(ListField(IntegerField), default=[[0], [0]])  # words, xp

    # Season
    xp = IntegerField(default=0)

    # Typing
    highspeed = DictField(
        StringField(),
        EmbeddedField(Score),
        default={},
    )
    verified = FloatField(default=0.0)

    # Other statistics
    scores = ListField(EmbeddedField(Score), default=[])
    achievements = DictField(StringField(), DateTimeField, default=[])  # id: timestamp
    medals = ListField(IntegerField, default=[0, 0, 0, 0])

    # Cosmetics
    badges = ListField(StringField, default=[])
    status = StringField(default="")

    # Streak of playing
    streak = IntegerField(default=0)  # days
    last_streak = DateTimeField(default=datetime.min)

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
    links = DictField(StringField(), StringField(), default={})
    pacer = StringField(default="")  # "", "avg", "rawavg", "pb", "INTEGER"

    @property
    def username(self):
        return f"{self.name}#{self.discriminator}"


class Mongo(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = AsyncIOMotorClient(bot.config.DATABASE_URI, io_loop=bot.loop)[
            bot.config.DATABASE_NAME
        ]
        instance = MotorAsyncIOInstance(self.db)

        g = globals()

        for n in (
            "Infraction",
            "Score",
            "User",
        ):

            setattr(self, n, instance.register(g[n]))
            getattr(self, n).bot = bot

    async def fetch_user(self, user: Union[discord.Member, int], create=False):
        if isinstance(user, int):
            user_id = user
        else:
            user_id = user.id

        # Checking if the user is in the cache
        u = self.bot.user_cache.get(user_id)
        if u is not None:
            u = self.User.build_from_mongo(pickle.loads(u))

        if u is not None and create is False:
            return u

        if u is None:
            u = await self.User.find_one({"id": user_id})
            if u is None:
                if not isinstance(user, int) and not user.bot:
                    u = self.User(
                        id=user.id,
                        name=user.name,
                        discriminator=user.discriminator,
                        avatar=user.avatar.key if user.avatar else None,
                    )
                    try:
                        await u.commit()
                    except pymongo.errors.DuplicateKeyError:
                        pass

                    # Caching user
                    self.bot.user_cache[user.id] = pickle.dumps(u.to_mongo())

                else:
                    self.bot.user_cache[user.id] = None
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
        self.bot.user_cache[user.id] = pickle.dumps(uj)

        return u

    def get_current(self, user):
        return {
            "name": user.name,
            "discriminator": user.discriminator,
            "avatar": user.avatar.key if user.avatar else None,
        }

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

        await self.db.user.update_one({"_id": user_id}, query)

        if user_id in self.bot.user_cache:
            del self.bot.user_cache[user_id]

    async def replace_user_data(self, user, user_data):
        if isinstance(user, int):
            user_id = user
        else:
            user_id = user.id

        await self.update_user(user, {"$set": user_data})

        # Caching new user data
        self.bot.user_cache[user_id] = pickle.dumps(user_data)

    async def ban_user(self, user, moderator: str, reason: str):
        inf = self.Infraction(
            moderator=moderator,
            reason=reason,
            timestamp=datetime.now(),
        )

        await self.update_user(
            user, {"$push": {"infractions": inf.to_mongo()}, "$set": {"banned": True}}
        )

        timestamp = round(time.time())

        # Logging ban
        embed = self.bot.error_embed(
            title=f"User Banned",
            description=(
                f"**User:** {user} ({user.id})\n"
                f"**Moderator:** {moderator}\n"
                f"**Reason:** {reason}\n"
                f"**Timestamp:** <t:{timestamp}:R>"
            ),
            add_footer=False,
        )

        await self.bot.impt_wh.send(embed=embed)


def setup(bot):
    bot.add_cog(Mongo(bot))
