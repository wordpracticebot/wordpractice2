import asyncio
import time
from datetime import datetime, timedelta

import numpy as np
from discord.ext import commands, tasks

from config import DBL_TOKEN, TESTING
from data.constants import AVG_AMT, CHALLENGE_AMT, UPDATE_24_HOUR_INTERVAL


class Tasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # For guild and shard count
        self.headers = {
            "Authorization": DBL_TOKEN,
        }

        if TESTING is False:
            if DBL_TOKEN is not None:
                self.post_guild_count.start()

            for u in [self.update_24_hour, self.daily_restart]:
                u.start()

        for u in [self.update_percentiles, self.clear_cooldowns]:
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
            await self.bot.redis.hdel("user", *all_ids)

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
                        "wpm": {"$sum": {"$slice": ["$scores.wpm", AVG_AMT]}},
                        "raw": {"$sum": {"$slice": ["$scores.raw", AVG_AMT]}},
                        "acc": {"$sum": {"$slice": ["$scores.acc", AVG_AMT]}},
                        "amt": {"$size": "$scores"},
                    }
                }
            ]
        )

        total = zip(
            *[
                (
                    m["wpm"] / (score_amt := min(m["amt"], AVG_AMT)),
                    m["raw"] / score_amt,
                    m["acc"] / score_amt,
                )
                async for m in a
                if m["amt"] != 0
            ]
        )

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

    @tasks.loop(minutes=10)
    async def post_guild_count(self):
        await self.bot.wait_until_ready()

        if self.post_guild_count.current_loop != 0:
            payload = {
                "server_count": len(self.bot.guilds),
                "shard_count": len(self.bot.shards),
            }

            url = f"https://top.gg/api/bots/{self.bot.user.id}/stats"

            async with self.bot.session.request(
                "POST", url, headers=self.headers, data=payload
            ) as resp:
                assert resp.status == 200

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

        # Just removing all users from the cache
        a = await self.bot.redis.hgetall("user")

        await self.bot.redis.hdel("user", *a.keys())

        # Updating all the leaderboards

        for lb in self.bot.lbs:
            for stat in lb.stats:
                # Wiping the leaderboard
                total = await self.bot.redis.zcard(stat.lb_key)
                await self.bot.redis.zremrangebyrank(stat.lb_key, 0, total)

                stat_pairs = await stat.update()

                await self.bot.redis.zadd(stat.lb_key, stat_pairs)

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
