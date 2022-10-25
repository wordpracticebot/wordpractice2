import asyncio
import time
from datetime import datetime, timedelta

import numpy as np
from discord.ext import commands, tasks

from config import DBL_TOKEN, TESTING
from data.constants import AVG_AMT, CHALLENGE_AMT, LB_LENGTH
from helpers.utils import run_in_executor


@run_in_executor(include_bot=True)
def _compile_lb_stats(bot, users):
    lbs = {}

    for u in users:
        values = bot.get_leaderboard_values(u)

        for i, lb in enumerate(values):
            for n, stat in enumerate(lb):
                name = f"lb.{i}.{n}"
                lbs[name] = lbs.get(name, []) + [(u.id, stat)]

    return lbs


class Tasks(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # For guild and shard count
        self.headers = {
            "Authorization": DBL_TOKEN,
        }

        if TESTING is False:
            if DBL_TOKEN is not None:
                self.post_guild_count.start()

        self.daily_restart.start()
        self.update_lbs.start()

        for u in [self.update_percentiles, self.clear_cooldowns]:
            u.start()

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

    @tasks.loop(minutes=15)
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
        # Removing users whose 24h stats have not been updated in the last 24h
        await self.bot.mongo.db.users.update_many(
            {
                "last_24h_save": {
                    "$lt": datetime.utcnow() - timedelta(days=1),
                },
            },
            {"$set": {"raw_words_24h": [], "raw_xp_24h": []}},
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

    @tasks.loop(hours=3)
    async def update_lbs(self):
        await self.bot.wait_until_ready()

        # Updating all the leaderboards

        # Querying all the users and evaluating their scores

        cursor = self.bot.mongo.User.find()

        users = [u async for u in cursor]

        lbs = await _compile_lb_stats(self.bot, users)

        for lb, values in lbs.items():
            # Sorting the scores and trimming to leaderboard length
            sorted_values = sorted(values, key=lambda x: x[1], reverse=True)[:LB_LENGTH]

            # Wiping the current leaderboard
            await self.bot.redis.zremrangebyrank(lb, 0, -1)

            # Saving the scores to the leaderboard
            await self.bot.redis.zadd(lb, dict(sorted_values))

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
