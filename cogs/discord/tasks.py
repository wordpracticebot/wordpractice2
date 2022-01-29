import asyncio
from datetime import datetime, timedelta
from typing import Union

from discord.ext import commands, tasks

from constants import COMPILE_INTERVAL, LB_LENGTH, UPDATE_24_HOUR_INTERVAL


class Tasks(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def get_sorted_lb(self, query: Union[list, dict]) -> list:
        cursor = self.bot.mongo.db.user.aggregate(
            [
                {
                    "$project": {
                        "_id": 1,
                        "username": 1,
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

    async def reset_24_hour_stats(self):
        pass

    async def recompile_leaderboards(self):
        pass

    @tasks.loop(hours=24)
    async def daily_start(self):
        pass

    @tasks.loop(minutes=UPDATE_24_HOUR_INTERVAL)
    async def update_24_hour(self):
        pass

    @tasks.loop(minutes=COMPILE_INTERVAL)
    async def update_leaderboards(self):
        pass

    @tasks.loop(minutes=30)
    async def post_guild_count(self):
        pass

    @tasks.loop(hours=24)
    async def restart_day(self):
        pass

    # Makes sure that the task only gets executed at the end of the day
    @restart_day.before_loop
    async def before_my_task(self):
        await self.bot.wait_until_ready()

        now = datetime.utcnow()

        future = datetime(now.year, now.month, now.day, 23, 59)
        if now.hour >= 23 and now.minute > 59:
            future += timedelta(days=1)

        await asyncio.sleep((future - now).seconds)


def setup(bot):
    bot.add_cog(Tasks(bot))
