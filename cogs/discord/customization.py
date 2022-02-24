import math

import discord
from discord.commands import Option, SlashCommandGroup
from discord.ext import commands

import icons
import word_list
from helpers.checks import cooldown, user_check
from helpers.converters import rqd_colour, opt_user
from helpers.errors import ImproperArgument
from helpers.ui import BaseView
from helpers.user import get_theme_display, get_pacer_display, get_pacer_type_name
from static import themes


class ThemeSelect(discord.ui.Select):
    def __init__(self, ctx):
        super().__init__(
            placeholder="Select a theme...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=name, emoji=discord.PartialEmoji.from_str(value["icon"])
                )
                for name, value in themes.default.items()
            ],
            row=1,
        )
        self.ctx = ctx

    async def update_theme(self, theme_value: list[str, str]):
        await self.ctx.bot.mongo.update_user(
            self.ctx.author, {"$set": {"theme": theme_value}}
        )

    async def callback(self, interaction):
        option = self.values[0]

        self.disabled = True

        theme_value = themes.default[option]["colours"]

        embed = self.ctx.custom_embed(
            title=f"{icons.success} Theme Selected",
            color=int(theme_value[1].replace("#", "0x"), 16),
            add_footer=False,
        )

        # TODO: generate a preview image

        await interaction.message.edit(embed=embed, view=None)

        await self.update_theme(theme_value)


def get_difficulty_choices(name):
    """Finds language difficulty options from selected language"""
    return word_list.languages.get(name, {"levels": []})["levels"]


class Customization(commands.Cog):
    """Customization commands"""

    emoji = "\N{GEAR}"
    order = 3

    def __init__(self, bot):
        self.bot = bot

    theme_group = SlashCommandGroup("theme", "Change the typing test theme")
    pacer_group = SlashCommandGroup("pacer", "Set a pacer for your typing test")

    # Calculates perceptual distance between two colours
    # Formula from: https://gist.github.com/ryancat/9972419b2a78f329ce3aebb7f1a09152
    def get_perceptual_distance(self, c1, c2):
        c1 = math.sqrt(c1[1] * c1[1] + c1[2] * c1[2])
        c2 = math.sqrt(c2[1] * c2[1] + c2[2] * c2[2])

        delta_c = c1 - c2
        delta_h = (c1 - c2) ** 2 + (c1 - c2) ** 2 - delta_c * delta_c
        delta_h = 0 if delta_h < 0 else math.sqrt(delta_h)

        sc = 1.0 + 0.045 * c1
        sh = 1.0 + 0.015 * c1

        delta_lklsl = (c1 - c2) / (1.0)
        delta_ckcsc = delta_c / (sc)
        delta_hkhsh = delta_h / (sh)

        i = (
            delta_lklsl * delta_lklsl
            + delta_ckcsc * delta_ckcsc
            + delta_hkhsh * delta_hkhsh
        )

        return max(int(math.sqrt(i)) + 1, 0)

    @cooldown(8, 3)
    @theme_group.command()
    async def custom(self, ctx, background: rqd_colour(), text: rqd_colour()):
        """Create a custom theme for your typing test"""

        distance = self.get_perceptual_distance(background, text)

        # Warning if the perceptual distance is too low
        if distance < 45:
            embed = ctx.embed(
                title=f"{icons.caution} Custom Theme Applied",
                description="Low colour contrast detected!",
                add_footer=False,
            )
        else:
            embed = ctx.embed(
                title=f"{icons.success} Custom Theme Applied", add_footer=False
            )

        # TODO: actually update the theme in the database

        await ctx.respond(embed=embed)

    @cooldown(8, 3)
    @theme_group.command()
    async def premade(self, ctx):
        """Choose a premade theme for your typing test"""
        view = BaseView(ctx, personal=True)
        view.add_item(ThemeSelect(ctx))

        await ctx.respond(content="** **", view=view)

    @cooldown(8, 3)
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

        embed = ctx.embed(
            title=f"{icons.success} Language changed to: `{name.capitalize()} {difficulty.capitalize()}`",
            add_footer=False,
        )

        await ctx.respond(embed=embed)

        # Updating the language after to be more responsive
        await self.bot.mongo.update_user(
            ctx.author, {"$set": {"language": name, "level": difficulty}}
        )

    async def handle_update_pacer(self, ctx, name, value):
        embed = ctx.embed(
            title=f"{icons.success} Updated pacer to: `{name}`", add_footer=False
        )
        await ctx.respond(embed=embed)

        # not inefficient because the user document is most likely cached from checking for ban
        user = await ctx.bot.mongo.fetch_user(ctx.author)

        if user.pacer_speed != value:
            await ctx.bot.mongo.update_user(
                ctx.author, {"$set": {"pacer_speed": value}}
            )

    @cooldown(8, 3)
    @pacer_group.command()
    async def pb(self, ctx):
        """Set your typing test pacer to your personal best"""
        await self.handle_update_pacer(ctx, "Personal Best", "pb")

    @cooldown(8, 3)
    @pacer_group.command()
    async def average(self, ctx):
        """Set your typing test pacer to your average speed"""
        await self.handle_update_pacer(ctx, "Average", "avg")

    @cooldown(8, 3)
    @pacer_group.command()
    async def rawaverage(self, ctx):
        """Set your typing test pacer to your raw average speed"""
        await self.handle_update_pacer(ctx, "Raw Average", "rawavg")

    @cooldown(8, 3)
    @pacer_group.command()
    async def off(self, ctx):
        """Turn off your typing test pacer"""
        await self.handle_update_pacer(ctx, "Off", "")

    @cooldown(8, 3)
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

        await self.handle_update_pacer(ctx, f"{speed} wpm", str(speed))

    @cooldown(8, 3)
    @commands.slash_command()
    async def equip(self, ctx):
        """Equip a badge that you own"""
        # Going to use a drop down menu
        pass

    @cooldown(5, 2)
    @commands.slash_command()
    async def settings(self, ctx, user: opt_user()):
        """View user settings"""

        user = await user_check(ctx, user)

        embed = ctx.embed(
            title=f"{user.username}'s Settings",
        )

        theme_name, theme_icon = get_theme_display(user.theme)

        theme_name = theme_name or "Custom"

        embed.add_field(
            name="Theme",
            value=f"{theme_icon} {theme_name} ({user.theme[0]} {user.theme[1]})",
            inline=False,
        )

        embed.add_field(
            name="Language",
            value=f"{user.language.capitalize()} ({user.level.capitalize()})",
            inline=False,
        )

        pacer_type_name = get_pacer_type_name(user.pacer_type)

        pacer_name = get_pacer_display(user.pacer_speed)

        if pacer_name != "None":
            pacer_name += f" ({pacer_type_name})"

        embed.add_field(name="Pacer", value=pacer_name, inline=False)

        embed.add_field(
            name="Premium", value="Yes" if user.premium else "No", inline=False
        )

        embed.set_thumbnail(url="https://i.imgur.com/2vUD4NF.png")

        await ctx.respond(embed=embed)

    @cooldown(8, 3)
    @commands.slash_command()
    async def link(
        self,
        ctx,
        website: Option(
            str,
            "Choose a typing website",
            choices=["Nitro Type", "10FastFingers", "Typeracer"],
            required=True,
        ),
        username: Option(str, "Enter your username / id", required=True),
    ):
        """Link your your typing website account to your profile"""
        if len(username) not in range(1, 20):
            raise commands.BadArgument("Username must be between 1 and 20 characters")


def setup(bot):
    bot.add_cog(Customization(bot))
