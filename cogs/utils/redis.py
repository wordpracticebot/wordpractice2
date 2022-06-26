from discord.ext import commands
from redis import asyncio as aioredis

from config import REDIS_URL


class Redis(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.pool = None
        self._connect_task = self.bot.loop.create_task(self.connect())

    async def connect(self):
        self.pool = await aioredis.from_url(
            REDIS_URL, socket_timeout=10, max_connections=10
        )

    async def wait_until_ready(self):
        await self._connect_task


def setup(bot):
    bot.add_cog(Redis(bot))
