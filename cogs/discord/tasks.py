import asyncio
import json
import time
from datetime import datetime, timedelta

import numpy as np
from discord.ext import commands, tasks

from config import DBL_TOKEN, TESTING
from constants import COMPILE_INTERVAL, UPDATE_24_HOUR_INTERVAL


def to_json(value):
    if json.__name__ == "ujson":
        return json.dumps(value, ensure_ascii=True)
    return json.dumps(value, separators=(",", ":"), ensure_ascii=True)


class Tasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # For guild and shard count
        self.headers = {
            "User-Agent": "wordPractice",
            "Content-Type": "application/json",
            "Authorization": DBL_TOKEN,
        }
        self.url = "https://top.gg/api/bots/stats"

        for u in [
            self.update_leaderboards,
            self.update_24_hour,
            self.post_guild_count,
            self.daily_restart,
            self.clear_cooldowns,
            self.update_percentiles,
        ]:
            u.start()

    @tasks.loop(minutes=UPDATE_24_HOUR_INTERVAL)
    async def update_24_hour(self):
        every = int(1440 / UPDATE_24_HOUR_INTERVAL) - 1

        self.bot.user_cache = {}

        # Have to update each field in two steps because of update conflict

        await self.bot.mongo.db.users.update_many(
            {f"last24.0.{every}": {"$exists": True}},
            {"$pop": {"last24.0": -1}},
        )
        await self.bot.mongo.db.users.update_many(
            {f"last24.0.{every-1}": {"$exists": True}},
            {"$push": {"last24.0": 0}},
        )

        await self.bot.mongo.db.users.update_many(
            {f"last24.1.{every}": {"$exists": True}},
            {"$pop": {"last24.1": -1}},
        )
        await self.bot.mongo.db.users.update_many(
            {f"last24.1.{every-1}": {"$exists": True}},
            {"$push": {f"last24.1": 0}},
        )

        # Resetting the best score in the last 24 hours
        await self.bot.mongo.db.users.update_many(
            {"best24": {"$ne": None}}, {"$set": {"best24": None}}
        )

    @tasks.loop(minutes=COMPILE_INTERVAL)
    async def update_leaderboards(self):
        for lb in self.bot.lbs:
            await lb.update_all()

        self.bot.last_lb_update = time.time()

    # Updates the typing average percentile
    # Is updated infrequently because it provides an estimate
    @tasks.loop(hours=12)
    async def update_percentiles(self):
        # Fetching the average wpm, raw and acc for every user in their last 10 tests
        a = self.bot.mongo.db.users.aggregate(
            [
                {
                    "$project": {
                        "_id": 0,
                        "wpm": {"$sum": {"$slice": ["$scores.wpm", 10]}},
                        "raw": {"$sum": {"$slice": ["$scores.raw", 10]}},
                        "acc": {"$sum": {"$slice": ["$scores.acc", 10]}},
                    }
                }
            ]
        )

        total = zip(*[(m["wpm"], m["raw"], m["acc"]) async for m in a])

        new_perc = []

        # Calculating the percentile for each category
        for t in total:
            new_perc.append(
                [
                    np.percentile(t, 33),
                    np.percentile(t, 66),
                ]
            )

        self.bot.avg_perc = new_perc

    @tasks.loop(minutes=30)
    async def post_guild_count(self):
        if TESTING or DBL_TOKEN is None:
            return

        await self.bot.wait_until_ready()

        # Making sure that all the guilds and shards have been loaded
        await asyncio.sleep(5)

        payload = {
            "server_count": len(self.bot.guilds),
            "shard_count": len(self.bot.shards),
        }

        payload = to_json(payload)

        async with self.bot.session.request(
            "POST", self.url, headers=self.headers, data=payload
        ) as resp:
            assert resp.status == 200

    @tasks.loop(hours=24)
    async def daily_restart(self):
        # Removing excess items if user hasn't typed in last 24 hours
        await self.bot.mongo.db.users.update_many(
            {"last24.0": [0] * 96},
            {"$set": {"last24.0": [0]}},
        )
        await self.bot.mongo.db.users.update_many(
            {"last24.1": [0] * 96},
            {"$set": {"last24.1": [0]}},
        )

        # Resetting daily challenge completions and tests
        await self.bot.mongo.db.users.update_many(
            {"is_daily_completed": True}, {"$set": {"is_daily_completed": False}}
        )
        await self.bot.mongo.db.users.update_many({}, {"$set": {"test_amt": 0}})

    # Clearing cache
    @tasks.loop(minutes=10)
    async def clear_cooldowns(self):
        # Removes cooldowns that have already expired
        for c in self.bot.cooldowns.copy():
            if time.time() > self.bot.cooldowns[c]:
                del self.bot.cooldowns[c]

    # Makes sure that the task only gets executed at the end of the day
    @daily_restart.before_loop
    async def before_my_task(self):
        await self.bot.wait_until_ready()

        now = datetime.utcnow()

        future = datetime(now.year, now.month, now.day, 23, 59)
        if now.hour >= 23 and now.minute > 59:
            future += timedelta(days=1)

        await asyncio.sleep((future - now).seconds)


def setup(bot):
    bot.add_cog(Tasks(bot))
