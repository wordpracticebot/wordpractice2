from collections import namedtuple

import discord
from discord.ext import commands
from rapidfuzz import fuzz, process
from rapidfuzz.utils import default_process
from helpers.utils import filter_commands

import constants
from helpers.ui import Base_View

Category = namedtuple("Category", ["name", "description", "cogs"])


def add_commands(embed, ctx, cmds):
    """Formats commands fields and adds them to embeds"""
    for cmd in cmds:
        embed.add_field(
            name=f"{ctx.prefix}{cmd} {cmd.signature}",
            value=cmd.help or "No command description",
            inline=False,
        )

    return embed


class Category_Selector(discord.ui.Select):
    def __init__(self, cogs):
        super().__init__(
            placeholder="Select a category",
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
        for _, cog in self.cogs.values():

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


class Help_View(Base_View):
    def __init__(self, ctx, default_page):
        super().__init__(ctx)

        self.default_page = default_page

    async def create_page(self, option):
        if option == "Welcome":
            # TODO: add more information about commands like typing test
            embed = self.ctx.bot.embed(
                title="Help",
                description="Welcome to wordPractice!",
            )
            embed.add_field(
                name="What is wordPractice?",
                value=(
                    "wordPractice most feature dense typing test Discord Bot.\n"
                    "Practice your typing skills while having fun by competing in seasons,\n"
                    "racing against others, collecting badges and much more!"
                ),
                inline=False,
            )
            embed.add_field(
                name="Support",
                value=(
                    "If you need any help or just want to talk about typing,\n"
                    f"join our community discord server at\n{constants.SUPPORT_SERVER}"
                ),
                inline=False,
            )
            return embed

        cmds, cog = option

        embed = self.ctx.bot.embed(
            title=f"{cog.qualified_name} Commands",
            description=cog.description or "No category description",
            add_footer=False,
        )

        embed = add_commands(embed, self.ctx, cmds)

        return embed

    async def update_message(self, interaction, option):
        embed = await self.create_page(option)
        await interaction.message.edit(embed=embed, view=self)

    async def start(self):
        embed = await self.create_page(self.default_page)
        self.response = await self.ctx.reply(embed=embed, view=self)


class Custom_Help(commands.HelpCommand):
    def __init__(self):
        super().__init__(command_attrs={"help": "Help command"})

    async def command_callback(self, ctx, *, command: str = None):
        # List of categories and commands
        if command is None:
            return await self.help_all()

        # To prioritize cogs (categories)
        command = command.capitalize()

        # For help with a specific cog, command or subcommand
        await super().command_callback(ctx, command=command)

    async def help_all(self):
        default_page = "Welcome"

        ctx = self.context

        # name: [commands, cog object]
        cogs = {
            cog.qualified_name: [m, cog]
            for cog in ctx.bot.cogs.values()
            if len(m := await filter_commands(ctx, cog.walk_commands(), sort=True))
        }

        view = Help_View(self.context, default_page)

        view.add_item(Category_Selector(cogs=cogs))

        await view.start()

    async def send_group_help(self, group):
        ctx = self.context

        embed = ctx.bot.embed(title=f"{group.qualified_name}")

        embed = add_commands(
            embed, ctx, await filter_commands(ctx, group.commands, sort=True)
        )

        await ctx.reply(embed=embed)

    async def send_command_help(self, cmd):
        ctx = self.context

        embed = ctx.bot.embed(title=f"{cmd.qualified_name.capitalize()}")

        embed = add_commands(embed, ctx, [cmd])

        if cmd.aliases:
            embed.add_field(name="Aliases", value="\n".join(cmd.aliases), inline=False)

        await ctx.reply(embed=embed)

    async def send_cog_help(self, cog):
        ctx = self.context

        embed = ctx.bot.embed(
            title=cog.qualified_name,
            description=cog.description or "No category description",
        )

        embed = add_commands(
            embed, ctx, await filter_commands(ctx, cog.commands, sort=True)
        )

        await ctx.reply(embed=embed)

    async def get_help_options(self):
        ctx = self.context

        options = set()

        for cmd in await filter_commands(ctx, ctx.bot.walk_commands()):
            options.add(str(cmd))

            if isinstance(cmd, commands.Command):
                # all aliases if it's just a command
                options.update(cmd.aliases)
            else:
                options.update(
                    f"{cmd.full_parent_name} {alias}" for alias in cmd.aliases
                )

            # Cog names (categories)
            options.add(cmd.cog_name)

        return options

    async def send_error_message(self, matches):
        ctx = self.context

        embed = ctx.bot.error_embed(
            title=f"Invalid Command",
            description=f"Type `{self.context.prefix}help` for a full list of commands",
            add_footer=False,
        )

        if matches != []:
            matches = "\n".join(f"`{m}`" for m in matches)
            embed.add_field(name="Did you mean", value=matches)

        await ctx.reply(embed=embed)

    async def command_not_found(self, string):
        choices = await self.get_help_options()
        result = process.extract(
            default_process(string),
            choices,
            scorer=fuzz.ratio,
            score_cutoff=60,
            processor=None,
        )

        return [match[0] for match in result[:3]]

    async def subcommand_not_found(self, command, string):
        return await self.command_not_found(f"{command.qualified_name} {string}")


class Misc(commands.Cog):
    """Miscellaneous commands"""

    def __init__(self, bot):
        self.bot = bot
        self.old_help = bot.help_command
        bot.help_command = Custom_Help()
        bot.help_command.cog = self

    @commands.command(aliases=["latency"])
    async def ping(self, ctx):
        """View the bot's latency"""

        # Discord API latency
        latency = round(self.bot.latency * 1000, 3)

        embed = self.bot.embed(title=f"Pong! {latency} ms", add_footer=False)

        await ctx.reply(embed=embed)

    def cog_unload(self):
        self.bot.help_command = self.old_help


def setup(bot):
    bot.add_cog(Misc(bot))
