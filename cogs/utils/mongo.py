import pickle
import time
from datetime import datetime

import discord
import pymongo
from discord.ext import commands
from motor.motor_asyncio import AsyncIOMotorClient
from umongo import Document, EmbeddedDocument, validate
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

import constants


class Guild(Document):

    # Server id
    id = IntegerField(attribute="_id")

    # Server prefix
    prefix = StringField(default=constants.DEFAULT_PREFIX)

    # # Disabled channels
    disabled = ListField(IntegerField, default=[])


class Infraction(EmbeddedDocument):
    moderator = StringField()  # NAME#DISCRIMINATOR (ID)
    reason = StringField()
    timestamp = DateTimeField()


class Score(EmbeddedDocument):
    wpm = FloatField()
    raw = FloatField()
    acc = FloatField()

    # correct words
    cw = IntegerField()
    # total words
    tw = IntegerField()

    # User input
    u_input = StringField(validate=[validate.Length(max=750)])

    # Quote
    quote = ListField(StringField)

    # coin earnings
    earnings = IntegerField()
    timestamp = DateTimeField()


class User(Document):
    # General member information
    id = IntegerField(attribute="_id")
    name = StringField(required=True)
    discriminator = IntegerField(required=True)
    avatar = StringField(default=None)

    # Statistics
    coins = StringField(default=0)
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
            "Guild",
            "Infraction",
            "Score",
            "User",
        ):

            setattr(self, n, instance.register(g[n]))
            getattr(self, n).bot = bot

    async def fetch_guild(self, guild: discord.Guild):
        g = await self.Guild.find_one({"id": guild.id})
        if g is None:
            g = self.Guild(id=guild.id)
            try:
                await g.commit()
            except pymongo.errors.DuplicateKeyError:
                pass
        return g

    async def fetch_user(self, user: discord.Member):
        # Checking if the user is in the cache
        u = self.bot.user_cache.get(user.id)
        if u is not None:
            u = self.User.build_from_mongo(pickle.loads(u))
        else:
            u = await self.User.find_one({"id": user.id})
            if u is None:
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

                return u

        current = {
            "name": user.name,
            "discriminator": user.discriminator,
            "avatar": user.avatar.key if user.avatar else None,
        }

        uj = u.to_mongo()

        # Checking if user info needs to be updated
        if current.values() != [u.name, u.discriminator, u.avatar]:
            await self.db.user.update_one({"_id": user.id}, {"$set": current})
            uj.update(current)

        # Updating in cache
        self.bot.user_cache[user.id] = pickle.dumps(uj)

        return u

    async def update_user(self, user, query: dict, del_cache=True):
        if hasattr(user, "id"):
            user = user.id

        await self.db.user.update_one({"_id": user}, query)

        if del_cache:
            if user in self.bot.user_cache:
                del self.bot.user_cache[user]

    async def ban_user(self, user, moderator: str, reason: str):
        inf = self.Infraction(
            moderator=moderator, reason=reason, timestamp=datetime.now()
        )
        await self.update_user(
            user, {"$set": {"banned": True}, "$push": {"infractions": inf.to_mongo()}}
        )

        timestamp = round(time.time())

        # TODO: improve embed display
        # Logging user ban
        embed = self.bot.embed(
            title="User Banned",
            description=(
                f"User: {user} ({user.id})\n"
                f"Moderator: {moderator}\n"
                f"Reason: {reason}\n"
                f"Timestamp: <t:{timestamp}:R>"
            ),
        )

        await self.bot.cmd_wh.send(embed=embed)


def setup(bot):
    bot.add_cog(Mongo(bot))
