from typing import Union

from discord.ext import commands, tasks

import constants


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
                {"$limit": constants.LB_LENGTH},
            ]
        )
        return [i async for i in cursor]


def setup(bot):
    bot.add_cog(Tasks(bot))
