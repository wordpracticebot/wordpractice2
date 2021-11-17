import discord
from discord.ext import commands


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    # Processing edited messages
    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if after.content != before.content:
            await self.bot.process_commands(after)


def setup(bot):
    bot.add_cog(Events(bot))
