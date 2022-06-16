import time
from datetime import datetime, timedelta
from textwrap import TextWrapper

import discord
from discord.ext import bridge, commands

import icons
from challenges.achievements import categories, get_achievement_display
from config import SUPPORT_GUILD_ID
from constants import (
    INFO_VIDEO,
    PRIVACY_POLICY_LINK,
    RULES_LINK,
    SUPPORT_SERVER_INVITE,
    SUPPORT_SERVER_VOTE_LINK,
    VOTING_SITES,
)
from helpers.checks import cooldown
from helpers.ui import BaseView, create_link_view
from helpers.utils import cmd_run_before, filter_commands, format_command

CREDITS = [
    [
        "Principle",
        [icons.dev_badge, icons.idea_badge],
        "Thank you for all the development done! Thomas would be proud",
    ],
    [
        "Harold",
        [icons.idea_badge, icons.artist_badge],
        "Just a cheese man eating cheese",
    ],
    [
        "Someone",
        [icons.idea_badge],
        "All hail the Cat Lady for her tireless efforts on the mod-team!",
    ],
    [
        "loboru",
        [icons.idea_badge],
        "Thank you so much for your initial support on the wordPractice project! Without your help, we could have never gotten here.",
    ],
    [
        "Miodec",
        [],
        "Consistency formula as well as typing words are derived from Miodec's Monkeytype. Thank you so much!",
    ],
    [
        "Freepik",
        [icons.artist_badge],
        "Thank you to freepik for the awesome free assets!",
    ],
]


def _add_commands(prefix, embed, cmds):
    """Formats commands fields and adds them to embeds"""

    wrapper = TextWrapper(width=55)

    for cmd in cmds:
        cmd_name = format_command(cmd)

        embed.add_field(
            name=f"{prefix}{cmd_name}",
            value="\n".join(wrapper.wrap(text=cmd.description or cmd.help))
            or "No command description",
            inline=False,
        )

    return embed


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
            embed = self.ctx.embed(
                title="Help",
                description="Welcome to wordPractice!",
            )
            embed.add_field(
                name="What is wordPractice?",
                value=(
                    "I'm the most feature dense typing test Discord Bot. I allow\n"
                    f"you to practice your typing skills while having fun!\n[Informational Video]({INFO_VIDEO})"
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
        )

        embed = _add_commands(self.ctx.prefix, embed, cmds)

        return embed

    async def update_message(self, interaction, option):
        embed = await self.create_page(option)
        await interaction.response.edit_message(embed=embed, view=self)

    async def start(self):
        embed = await self.create_page("Welcome")

        cogs = {
            cog.qualified_name: [m, cog]
            for cog in self.ctx.bot.cogs.values()
            if len(m := filter_commands(self.ctx, cog.walk_commands()))
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

    @bridge.bridge_command()
    async def ping(self, ctx):
        """View the bot's latency"""

        # Discord API latency
        latency = round(self.bot.latency * 1000, 3)

        embed = ctx.embed(title=f"Pong! {latency} ms", add_footer=False)

        await ctx.respond(embed=embed)

    @bridge.bridge_command()
    async def attribution(self, ctx):
        """View the bot's attribution"""
        embed = ctx.embed(
            title=f"{icons.dev_badge} | Attribution",
            description=(
                f"```Thank you to everyone who helped make this bot possible!```\n"
                f"**Development:** {icons.dev_badge}\n"
                f"**Ideas/Suggestions:** {icons.idea_badge}\n"
                f"**Art/Graphics:** {icons.artist_badge}\n\n** **"
            ),
        )

        for i, (name, badges, desc) in enumerate(CREDITS):
            if badges:
                badge_display = " | " + " ".join(badges)
            else:
                badge_display = ""

            embed.add_field(name=f"`{name}`{badge_display}", value=f"> {desc}\n\n** **")

            if i % 2 == 1:
                embed.add_field(name="** **", value="** **")

        await ctx.respond(embed=embed)

    @bridge.bridge_command(name="help")
    async def _help(self, ctx):
        """Help with bot usage and list of commands"""

        # longer timeout gives time for people to run the commands
        view = HelpView(ctx, timeout=30)

        await view.start()

    @cooldown(3, 1)
    @bridge.bridge_command()
    async def stats(self, ctx):
        """Various statistics related to the bot"""
        embed = ctx.embed(title="Bot Stats")

        uptime = time.time() - self.bot.start_time

        h = int(uptime // 3600)
        m = int(uptime % 3600 // 60)

        typist_count = await self.bot.mongo.db.users.estimated_document_count()

        embed.set_thumbnail(url=self.bot.user.display_avatar.url)

        embed.add_field(name="Servers", value=len(self.bot.guilds), inline=False)
        embed.add_field(name="Shards", value=len(self.bot.shards), inline=False)
        embed.add_field(name="Typists", value=typist_count, inline=False)
        embed.add_field(name="Uptime", value=f"{h} hrs {m} min", inline=False)

        await ctx.respond(embed=embed)

    @bridge.bridge_command()
    async def privacy(self, ctx):
        """View the privacy policy"""
        embed = ctx.embed(
            title="Privacy Policy",
            description=f"If you have any questions, join\nour [support server]({SUPPORT_SERVER_INVITE})",
            add_footer=False,
        )
        embed.set_thumbnail(url="https://i.imgur.com/CBl34Rv.png")

        view = create_link_view(
            {
                "Privacy Policy": PRIVACY_POLICY_LINK,
            }
        )

        await ctx.respond(embed=embed, view=view)

    @bridge.bridge_command()
    async def rules(self, ctx):
        """View the rules"""
        embed = ctx.embed(
            title="Rules",
            description=f"If you have any questions, join\nour [support server]({SUPPORT_SERVER_INVITE})",
            add_footer=False,
        )

        embed.set_thumbnail(url="https://i.imgur.com/HCntMH9.png")

        view = create_link_view(
            {
                "Rules": RULES_LINK,
            }
        )

        await ctx.respond(embed=embed, view=view)

    @bridge.bridge_command()
    async def invite(self, ctx):
        """Get the invite link for the bot"""

        view = create_link_view(
            {
                "Invite Bot": self.bot.create_invite_link(),
                "Community Server": SUPPORT_SERVER_INVITE,
            }
        )

        await ctx.respond("Here you go!", view=view)

    @bridge.bridge_command()
    async def support(self, ctx):
        """Join the wordPractice Discord server"""
        await ctx.respond(SUPPORT_SERVER_INVITE)

    @bridge.bridge_command()
    async def vote(self, ctx):
        """Get the voting link for the bot"""

        user = ctx.initial_user

        embed = ctx.embed(
            title="Vote for wordPractice",
            description=f":trophy: Total Votes: {user.votes}",
        )

        embed.add_field(
            name="Rewards per Vote", value=f"{icons.xp} 1000 XP", inline=False
        )

        # Voting achievement progress
        a = categories["Endurance"].challenges[1]

        a, emoji, display, bar_display = await get_achievement_display(ctx, user, a)

        embed.add_field(
            name="** **",
            value="**Vote Achievement Progress:**",
            inline=False,
        )

        embed.add_field(
            name=f"**{emoji} {a.name}{display}**", value=bar_display, inline=False
        )

        view = discord.ui.View()

        for name, value in VOTING_SITES.items():
            next_vote = timedelta(hours=value["time"]) + user.last_voted[name]

            if datetime.utcnow() >= next_vote:
                button = discord.ui.Button(label=value["name"], url=value["link"])
            else:
                time_until = next_vote - datetime.utcnow()

                button = discord.ui.Button(
                    label=f"{value['name']} - {max(time_until.seconds // 3600, 1)}h",
                    style=discord.ButtonStyle.gray,
                    disabled=True,
                )

            view.add_item(button)

        await ctx.respond(embed=embed, view=view)

        if not cmd_run_before(ctx, user):
            msg = "Voting is a great way to support wordPractice!"

            await ctx.respond(msg, ephemeral=True)

        if ctx.guild.id == SUPPORT_GUILD_ID:
            view = create_link_view({"Server Voting Link": SUPPORT_SERVER_VOTE_LINK})

            await ctx.respond(
                "Get the `Voter` role by voting for the server!",
                view=view,
                ephemeral=True,
            )


def setup(bot):
    bot.add_cog(Misc(bot))
