import discord
from discord.commands import Option, SlashCommandGroup
from discord.ext import commands

import word_list
from helpers.converters import rqd_colour
from helpers.errors import ImproperArgument


def get_difficulty_choices(name):
    """Finds language difficulty options from selected language"""
    return word_list.languages.get(name, {"levels": []})["levels"]


class Customization(commands.Cog):
    """Customization commands"""

    def __init__(self, bot):
        self.bot = bot

    theme_group = SlashCommandGroup("theme", "Change the typing test theme")

    @theme_group.command()
    async def custom(self, ctx, background: rqd_colour(), text: rqd_colour()):
        """Create a custom theme for your typing test"""
        pass

    @theme_group.command()
    async def premade(self, ctx):
        """Choose a premade theme for your typing test"""
        # TODO: use a dropdown with custom emojis
        pass

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


def setup(bot):
    bot.add_cog(Customization(bot))
