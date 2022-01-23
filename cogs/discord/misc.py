import time
from datetime import datetime, timedelta

import discord
from discord.ext import commands

import icons
from achievements import categories, get_achievement_tier, get_bar
from constants import VOTING_SITES
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

        user = await self.bot.mongo.fetch_user(ctx.author)

        embed = self.bot.embed(title="Vote for wordPractice", add_footer=False)

        embed.add_field(name="Rewards", value=f"{icons.xp} 1000 xp", inline=False)

        # Voting achievement progress
        all_achievements = categories["Endurance"].challenges[1]

        names = [i.name for i in all_achievements]
        tier = get_achievement_tier(user, names)

        a = all_achievements[tier]

        p = a.progress(user)

        bar = get_bar(p[0] / p[1])

        embed.add_field(
            name="Vote Achievement Progress",
            value=f">>> **Reward:** {a.reward}\n{bar} `{p[0]}/{p[1]}`",
            inline=False,
        )

        view = discord.ui.View()

        for name, value in VOTING_SITES.items():
            next_vote = timedelta(hours=value["time"]) + user.last_voted[name]

            if datetime.now() >= next_vote:
                button = discord.ui.Button(label=name, url=value["link"])
            else:
                time_until = datetime.now() - next_vote

                button = discord.ui.Button(
                    label=f"{name} - {max(time_until.seconds // 3600, 1)}h",
                    style=discord.ButtonStyle.gray,
                    disabled=True,
                )

            view.add_item(button)

        await ctx.respond(embed=embed, view=view)


def setup(bot):
    bot.add_cog(Misc(bot))
