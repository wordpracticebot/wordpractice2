import discord
from discord.ext import commands


class Owner(commands.Cog):
    """Commands only for the owner"""

    def __init__(self, bot):
        self.bot = bot

    # TODO: get working better with folders

    async def cog_check(self, ctx):
        return await self.bot.is_owner(ctx.author)

    @commands.command(name="reload", hidden=True)
    async def _reload(self, ctx, ext: str):
        """Reloads an extension"""
        try:
            self.bot.reload_extension(f"cogs.{ext}")
        except Exception as e:
            await ctx.reply(f"{e.__class__.__name__}: {e}")
        else:
            await ctx.reply(f"Reloaded {ext}")

    @commands.command(hidden=True)
    async def unload(self, ctx, ext: str):
        """Unloads an extension"""
        try:
            self.bot.unload_extension(f"cogs.{ext}")
        except Exception as e:
            await ctx.reply(f"{e.__class__.__name__}: {e}")
        else:
            await ctx.reply(f"Unloaded {ext}")

    @commands.command(hidden=True)
    async def load(self, ctx, ext: str):
        try:
            self.bot.load_extension(f"cogs.{ext}")
        except Exception as e:
            await ctx.reply(f"{e.__class__.__name__}: {e}")
        else:
            await ctx.reply(f"Loaded {ext}")

    @commands.command(hidden=True)
    async def disable(self, ctx, cmd: str):
        """Disable a command"""
        if (cmd := self.bot.get_command(cmd)) is not None:
            cmd.enabled = False
            await ctx.reply(f"Disabled command: {cmd}")

    @commands.command(hidden=True)
    async def enable(self, ctx, cmd: str):
        """Enable a command"""
        if (cmd := self.bot.get_command(cmd)) is not None:
            cmd.enabled = True
            await ctx.reply(f"Enabled command: {cmd}")


def setup(bot):
    bot.add_cog(Owner(bot))
