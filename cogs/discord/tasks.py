from typing import Union

from discord.ext import commands, tasks

from constants import LB_LENGTH


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


def setup(bot):
    bot.add_cog(Tasks(bot))
