import time

from discord.ext import commands

from helpers.ui import create_link_view


class Misc(commands.Cog):
    """Miscellaneous commands"""

    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command()
    async def ping(self, ctx):
        """View the bot's latency"""

        # Discord API latency
        latency = round(self.bot.latency * 1000, 3)

        embed = self.bot.embed(title=f"Pong! {latency} ms", add_footer=False)

        await ctx.respond(embed=embed)

    @commands.slash_command()
    async def help(self, ctx):
        """List of commands"""
        pass

    @commands.slash_command()
    async def stats(self, ctx):
        """Various statistics related to the bot"""
        embed = self.bot.embed(title="Bot Stats")

        uptime = time.time() - self.bot.start_time

        h = int(uptime // 3600)
        m = int(uptime % 3600 // 60)

        typist_count = await self.bot.mongo.db.user.estimated_document_count()

        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        embed.add_field(name="Servers", value=len(self.bot.guilds), inline=False)
        embed.add_field(name="Shards", value=len(self.bot.shards), inline=False)
        embed.add_field(name="Typists", value=typist_count, inline=False)
        embed.add_field(name="Uptime", value=f"{h} hrs {m} min", inline=False)

        await ctx.respond(embed=embed)

    @commands.slash_command()
    async def privacy(self, ctx):
        """View the privacy policy"""
        pass

    @commands.slash_command()
    async def invite(self, ctx):
        """Get the invite link for the bot"""

        view = create_link_view({"Invite Bot": self.bot.create_invite_link()})

        await ctx.respond("Here you go!", view=view)

    @commands.slash_command()
    async def rules(self, ctx):
        """View the rules"""
        pass

    @commands.slash_command()
    async def vote(self, ctx):
        """Get the voting link for the bot"""
        pass


def setup(bot):
    bot.add_cog(Misc(bot))
