from static import themes
import discord
from discord.commands import Option, SlashCommandGroup
from discord.ext import commands

import word_list
from helpers.converters import rqd_colour
from helpers.errors import ImproperArgument
from helpers.ui import BaseView


class ThemeView(BaseView):
    def __init__(self, ctx, default_page):
        super().__init__(ctx)

        self.default_page = default_page

    async def create_page(self, selection):
        return self.ctx.bot.embed(title=f"{selection}")

    async def update_message(self, interaction, option):
        embed = await self.create_page(option)
        await interaction.message.edit(embed=embed, view=self)

    async def start(self):
        embed = await self.create_page(self.default_page)
        self.response = await self.ctx.respond(embed=embed, view=self)


class ThemeSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Select a theme",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=name, emoji=value["icon"])
                for name, value in themes.default.items()
            ],
        )

    async def callback(self, interaction):
        option = self.values[0]

        self.view.page = 1

        await self.view.update_message(interaction, option)


def get_difficulty_choices(name):
    """Finds language difficulty options from selected language"""
    return word_list.languages.get(name, {"levels": []})["levels"]


class Customization(commands.Cog):
    """Customization commands"""

    def __init__(self, bot):
        self.bot = bot

    theme_group = SlashCommandGroup("theme", "Change the typing test theme")
    pacer_group = SlashCommandGroup("pacer", "Set a pacer for your typing test")

    @theme_group.command()
    async def custom(self, ctx, background: rqd_colour(), text: rqd_colour()):
        """Create a custom theme for your typing test"""
        pass

    @theme_group.command()
    async def premade(self, ctx):
        """Choose a premade theme for your typing test"""
        # TODO: use a dropdown with custom emojis
        view = ThemeView(ctx, "Games")
        view.add_item(ThemeSelect())
        await view.start()

    @commands.slash_command()
    async def language(
        self,
        ctx,
        name: Option(str, "Choose a language", choices=word_list.languages.keys()),
        difficulty: Option(
            str,
            autocomplete=discord.utils.basic_autocomplete(
                lambda ctx: get_difficulty_choices(ctx.options.get("name"))
            ),
        ),
    ):
        """Choose a language for your typing test"""

        # Checking if difficulty is valid
        if difficulty not in (choices := get_difficulty_choices(name)):
            raise ImproperArgument(
                "That is not a valid difficulty", options=list(choices.keys())
            )

        await ctx.respond(f"language: {name} {difficulty}")

    @pacer_group.command()
    async def pb(self, ctx):
        """Set your typing test pacer to your personal best"""
        pass

    @pacer_group.command()
    async def average(self, ctx):
        """Set your typing test pacer to your average speed"""
        pass

    @pacer_group.command()
    async def custom(
        self,
        ctx,
        speed: Option(
            int,
            "Choose a pacer speed from 10-300",
            required=True,
        ),
    ):
        """Set your typing test pacer to a custom speed"""
        if speed not in range(10, 300):
            raise commands.BadArgument("Pacer speed must be between 10 and 300")

    @commands.slash_command()
    async def link(
        self,
        ctx,
        website: Option(
            str,
            "Choose a typing website",
            choices=["nitro type", "10fastfingers", "typeracer"],
            required=True,
        ),
        username: Option(str, "Enter your username / id", required=True),
    ):
        """Link your your typing website account to your profile"""
        if len(username) not in range(1, 20):
            raise commands.BadArgument("Username must be between 1 and 20 characters")


def setup(bot):
    bot.add_cog(Customization(bot))
