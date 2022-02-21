import time
from datetime import datetime, timedelta
from textwrap import TextWrapper

import discord
from discord.commands import SlashCommand, SlashCommandGroup
from discord.ext import commands

import icons
from achievements import categories, get_achievement_tier, get_bar
from constants import SUPPORT_SERVER_INVITE, VOTING_SITES
from helpers.ui import BaseView, create_link_view
from helpers.user import get_user_cmds_run


def _add_commands(embed, cmds):
    """Formats commands fields and adds them to embeds"""

    wrapper = TextWrapper(width=55)

    for cmd in cmds:
        embed.add_field(
            name=f"/{cmd.name}",
            value="\n".join(wrapper.wrap(text=cmd.description))
            or "No command description",
            inline=False,
        )

    return embed


async def _filter_commands(ctx, commands):
    iterator = filter(
        lambda c: isinstance(c, (SlashCommand, SlashCommandGroup)), commands
    )

    async def predicate(cmd):
        try:
            return await cmd.can_run(ctx)
        except commands.CommandError:
            return False

    ret = []
    for cmd in iterator:
        valid = await predicate(cmd)
        if valid:
            ret.append(cmd)

    return ret


class CategorySelect(discord.ui.Select):
    def __init__(self, cogs):
        super().__init__(
            placeholder="Select a Category...",
            min_values=1,
            max_values=1,
        )

        self.cogs = cogs

        self.add_options()

    def add_options(self):
        self.add_option(
            label="Welcome",
            description="Learn about the bot",
            emoji="\N{WAVING HAND SIGN}",
            value="Welcome",
        )

        for _, cog in sorted(
            self.cogs.values(),
            key=lambda c: getattr(
                c[1], "order", 1000
            ),  # 1000 is just an arbitrary high number so the category appears at the end if no order is specified
        ):
            self.add_option(
                label=cog.qualified_name,
                description=cog.description or "No category description",
                emoji=getattr(cog, "emoji", None),
                value=cog.qualified_name,
            )

    async def callback(self, interaction):
        option = self.values[0]

        if option != "Welcome":
            option = self.cogs[option]

        await self.view.update_message(interaction, option)


class HelpView(BaseView):
    async def create_page(self, option):
        if option == "Welcome":
            # TODO: add more information about how to start (maybe create a youtube video)
            embed = self.ctx.embed(
                title="Help",
                description="Welcome to wordPractice!",
                add_footer=False,
            )
            embed.add_field(
                name="What is wordPractice?",
                value=(
                    "I'm the most feature dense typing test Discord Bot. I allow\n"
                    "you to practice your typing skills while having fun!\n"
                ),
                inline=False,
            )
            embed.add_field(
                name="Support",
                value=(
                    "If you need any help or just want to talk about typing,\n"
                    f"join our community discord server at\n{SUPPORT_SERVER_INVITE}"
                ),
                inline=False,
            )
            embed.add_field(
                name="** **",
                value="Use the dropdown below to learn more about my commands.",
                inline=False,
            )
            return embed

        cmds, cog = option

        embed = self.ctx.embed(
            title=f"{cog.qualified_name} Commands",
            description=cog.description or "No category description",
            add_footer=False,
        )

        embed = _add_commands(embed, cmds)

        return embed

    async def update_message(self, interaction, option):
        embed = await self.create_page(option)
        await interaction.message.edit(embed=embed, view=self)

    async def start(self):
        embed = await self.create_page("Welcome")

        cogs = {
            cog.qualified_name: [m, cog]
            for cog in self.ctx.bot.cogs.values()
            if len(m := await _filter_commands(self.ctx, cog.walk_commands()))
        }

        selector = CategorySelect(cogs)

        self.add_item(item=selector)

        await self.ctx.respond(embed=embed, view=self)


class Misc(commands.Cog):
    """Miscellaneous commands"""

    emoji = "\N{CARD FILE BOX}"
    order = 4

    def __init__(self, bot):
        self.bot = bot

    @commands.slash_command()
    async def ping(self, ctx):
        """View the bot's latency"""

        # Discord API latency
        latency = round(self.bot.latency * 1000, 3)

        embed = ctx.embed(title=f"Pong! {latency} ms", add_footer=False)

        await ctx.respond(embed=embed)

    @commands.slash_command(name="help")
    async def _help(self, ctx):
        """Help with bot usage and list of ocmmands"""
        view = HelpView(
            ctx, timeout=30
        )  # longer timeout gives time for people to run the commands
        await view.start()

    @commands.slash_command()
    async def stats(self, ctx):
        """Various statistics related to the bot"""
        embed = ctx.embed(title="Bot Stats")

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

        view = create_link_view(
            {
                "Invite Bot": self.bot.create_invite_link(),
                "Community Server": SUPPORT_SERVER_INVITE,
            }
        )

        await ctx.respond("Here you go!", view=view)

    @commands.slash_command()
    async def rules(self, ctx):
        """View the rules"""
        pass

    @commands.slash_command()
    async def vote(self, ctx):
        """Get the voting link for the bot"""

        user = await self.bot.mongo.fetch_user(ctx.author)

        embed = ctx.embed(title="Vote for wordPractice", add_footer=False)

        embed.add_field(
            name="Rewards per Vote", value=f"{icons.xp} 1000 xp", inline=False
        )

        # Voting achievement progress
        all_achievements = categories["Endurance"].challenges[1]

        names = [i.name for i in all_achievements]
        tier = get_achievement_tier(user, names)

        a = all_achievements[tier]

        p = a.progress(user)

        bar = get_bar(p[0] / p[1])

        embed.add_field(
            name="** **\nVote Achievement Progress",
            value=f">>> **Reward:** {a.reward}\n{bar} `{p[0]}/{p[1]}`",
            inline=False,
        )

        view = discord.ui.View()

        for name, value in VOTING_SITES.items():
            next_vote = timedelta(hours=value["time"]) + user.last_voted[name]

            if datetime.utcnow() >= next_vote:
                button = discord.ui.Button(label=name, url=value["link"])
            else:
                time_until = next_vote - datetime.utcnow()

                button = discord.ui.Button(
                    label=f"{name} - {max(time_until.seconds // 3600, 1)}h",
                    style=discord.ButtonStyle.gray,
                    disabled=True,
                )

            view.add_item(button)

        await ctx.respond(embed=embed, view=view)


def setup(bot):
    bot.add_cog(Misc(bot))
