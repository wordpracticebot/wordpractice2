import pickle
import time
from datetime import datetime

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
from typing import Union


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

    # coin earnings
    earnings = IntegerField(required=True)
    timestamp = DateTimeField(required=True)


class User(Document):
    # General member information
    id = IntegerField(attribute="_id")
    name = StringField(required=True)
    discriminator = IntegerField(required=True)
    avatar = StringField(default=None)

    # Statistics
    words = IntegerField(default=0)
    last24 = ListField(ListField(IntegerField), default=[[0], [0]])

    highspeed = ListField(EmbeddedField(Score), default=[])
    verified = FloatField(default=0.0)
    scores = ListField(EmbeddedField(Score), default=[])
    achievements = DictField(StringField(), DateTimeField, default={})  # id: timestamp

    # Cosmetics
    medals = ListField(IntegerField, default=[0, 0, 0, 0])
    badges = ListField(StringField, default=[])
    status = StringField(default="")

    # Streak
    streak = IntegerField(default=0)
    last_streak = DateTimeField(default=datetime.min)

    # Voting
    votes = IntegerField(default=0)
    last_voted = DateTimeField(default=datetime.min)

    # Infractions
    infractions = ListField(EmbeddedField(Infraction), default=[])
    banned = BooleanField(default=False)

    # Settings
    theme = ListField(StringField, default=["#ffffff", "#000000"])
    lang = StringField(default="english")
    links = DictField(StringField(), StringField(), default={})
    pacer = StringField(default="")  # "", "avg", "rawavg", "pb", "INTEGER"


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

    async def fetch_user(self, user: Union[discord.Member, int]):
        if isinstance(user, int):
            user_id = user
        else:
            user_id = user.id

        # Checking if the user is in the cache
        u = self.bot.user_cache.get(user_id)
        if u is not None:
            u = self.User.build_from_mongo(pickle.loads(u))
        else:
            u = await self.User.find_one({"id": user_id})
            if u is None:
                if user != user_id:
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
                    self.bot.user[user.id] = None
                    return None

                return u

        current = {
            "name": user.name,
            "discriminator": user.discriminator,
            "avatar": user.avatar.key if user.avatar else None,
        }

        uj = u.to_mongo()

        # Checking if user info needs to be updated
        if current.values() != [u.name, u.discriminator, u.avatar]:
            await self.update_user(user.id, {"$set": current})
            uj.update(current)

        # Updating in cache
        self.bot.user_cache[user.id] = pickle.dumps(uj)

        return u

    async def update_user(self, user, query: dict):
        if hasattr(user, "id"):
            user = user.id

        await self.db.user.update_one({"_id": user}, query)

        if user in self.bot.user_cache:
            del self.bot.user_cache[user]

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
