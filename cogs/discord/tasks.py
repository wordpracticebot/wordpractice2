import asyncio
import time
from datetime import datetime, timedelta

import numpy as np
from discord.ext import commands, tasks

from config import DBL_TOKEN, TESTING
from constants import CHALLENGE_AMT, COMPILE_INTERVAL, UPDATE_24_HOUR_INTERVAL


class Tasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # For guild and shard count
        self.headers = {
            "Authorization": DBL_TOKEN,
        }

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
        every = int(24 * 60 / UPDATE_24_HOUR_INTERVAL) - 1

        all_ids = set()

        for i in range(2):
            cursor = self.bot.mongo.db.users.find(
                {f"last24.{1}.{every}": {"$exists": True}}
            )

            user_ids = [u["_id"] async for u in cursor]

            # Has to be done in two queries because of update conflict
            await self.bot.mongo.db.users.update_many(
                {"_id": {"$in": user_ids}},
                {"$pop": {f"last24.{i}": -1}},
            )
            await self.bot.mongo.db.users.update_many(
                {"_id": {"$in": user_ids}},
                {"$push": {f"last24.{i}": 0}},
            )

            all_ids.update(user_ids)

        # Resetting the best score in the last 24 hours
        cursor = self.bot.mongo.db.users.find({"best24": {"$ne": None}})

        user_ids = [u["_id"] async for u in cursor]

        await self.bot.mongo.db.users.update_many(
            {"_id": {"$in": user_ids}},
            {"$set": {"best24": None}},
        )

        all_ids.update(user_ids)

        if all_ids:
            await self.bot.redis.hdel("users", *all_ids)

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

        payload = {
            "server_count": len(self.bot.guilds),
            "shard_count": len(self.bot.shards),
        }

        url = f"https://top.gg/api/bots/{self.bot.user.id}/stats"

        async with self.bot.session.request(
            "POST", url, headers=self.headers, data=payload
        ) as resp:
            assert resp.status == 200

    @post_guild_count.before_loop
    async def before_post_dbl(self):
        await self.bot.wait_until_ready()

    @tasks.loop(hours=24)
    async def daily_restart(self):
        # Removing excess items if user hasn't typed in last 24 hours

        cursor = self.bot.mongo.db.users.find(
            {"$or": [{"last24.0": [0] * 96}, {"last24.1": [0] * 96}]}
        )

        last24_ids = [u["_id"] async for u in cursor]

        await self.bot.mongo.db.users.update_many(
            {"_id": {"$in": last24_ids}},
            {"$set": {"last24.1": [0], "test_amt": 0, "last24.0": [0]}},
        )

        # Resetting daily challenge completions and tests
        default = [False] * CHALLENGE_AMT

        cursor = self.bot.mongo.db.users.find({"daily_completion": {"$ne": default}})

        daily_completion_ids = [u["_id"] async for u in cursor]

        await self.bot.mongo.db.users.update_many(
            {"_id": {"$in": daily_completion_ids}},
            {"$set": {"daily_completion": default}},
        )

        # Removing updated users from the cache
        users_to_remove = set(last24_ids + daily_completion_ids)

        if users_to_remove:
            await self.bot.redis.hdel("users", *users_to_remove)

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
