import asyncio
import time
from datetime import datetime, timedelta
from typing import Union

import numpy as np
from discord.ext import commands, tasks

from constants import COMPILE_INTERVAL, LB_LENGTH, UPDATE_24_HOUR_INTERVAL


class Tasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        for u in [
            self.update_leaderboards,
            self.update_24_hour,
            self.post_guild_count,
            self.daily_restart,
            self.clear_cooldowns,
            self.update_percentiles,
        ]:
            u.start()

    async def get_sorted_lb(self, query: Union[list, dict]) -> list:
        cursor = self.bot.mongo.db.users.aggregate(
            [
                {
                    "$project": {
                        "_id": 1,
                        "name": 1,
                        "discriminator": 1,
                        "status": 1,
                        "count": query,
                    }
                },
                {"$sort": {"count": -1}},
                {"$limit": LB_LENGTH},
            ]
        )
        return [i async for i in cursor]

    async def reset_extra_24_hour_stats(self):
        await self.bot.mongo.db.users.update_many(
            {"last24.0": [0] * 96},
            {"$set": {"last24.0": [0]}},
        )
        await self.bot.mongo.db.users.update_many(
            {"last24.1": [0] * 96},
            {"$set": {"last24.1": [0]}},
        )

    @tasks.loop(minutes=UPDATE_24_HOUR_INTERVAL)
    async def update_24_hour(self):
        every = 1440 / UPDATE_24_HOUR_INTERVAL - 1

        # Have to update each field in two steps because of update conflict

        await self.bot.mongo.db.users.update_many(
            {f"last24.0.{every}": {"$exists": True}},
            {"$pop": {"last24.0": -1}},
        )
        await self.bot.mongo.db.users.update_many(
            {f"last24.0.{every}": {"$exists": True}},
            {"$push": {"last24.0": 0}},
        )

        await self.bot.mongo.db.users.update_many(
            {f"last24.1.{every}": {"$exists": True}},
            {"$pop": {"last24.1": -1}},
        )
        await self.bot.mongo.db.users.update_many(
            {f"last24.1.{every}": {"$exists": True}},
            {"$push": {f"last24.1": 0}},
        )

    @tasks.loop(minutes=COMPILE_INTERVAL)
    async def update_leaderboards(self):
        lbs = []

        # 0 = 24hr
        # 1 = season
        # 2 = alltime
        # 3 = highspeed
        # 4 = recent scores

        # 24 hour leaderboards
        lbs.append(
            [
                await self.get_sorted_lb(
                    {"$sum": {"$arrayElemAt": ["$last24", 0]}}
                ),  # words
                await self.get_sorted_lb(
                    {"$sum": {"$arrayElemAt": ["$last24", 1]}}
                ),  # xp
            ]
        )

        # season leaderboards
        lbs.append(
            [
                await self.get_sorted_lb("$xp"),
            ]
        )

        # alltime leaderboards
        lbs.append(
            [
                await self.get_sorted_lb("$words"),
                await self.get_sorted_lb("$streak"),
            ]
        )

        # highspeed leaderboard
        lbs.append(
            [
                await self.get_sorted_lb("$highspeed.short.wpm"),
                await self.get_sorted_lb("$highspeed.medium.wpm"),
                await self.get_sorted_lb("$highspeed.long.wpm"),
            ]
        )

        # TODO: add a leaderboard for recent test scores

        self.bot.lbs = lbs
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
        # TODO: post guid count to top.gg
        pass

    @tasks.loop(hours=24)
    async def daily_restart(self):
        # Removing excess items if user hasn't typed in last 24 hours
        await self.reset_extra_24_hour_stats()

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
