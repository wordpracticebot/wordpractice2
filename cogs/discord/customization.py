import math

import discord
from discord.commands import Option, SlashCommandGroup
from discord.ext import bridge, commands

import data.icons as icons
import word_list
from bot import Context, WordPractice
from data.constants import (
    DEFAULT_WRAP,
    MIN_PACER_SPEED,
    PACER_PLANES,
    PREMIUM_LINK,
    STATIC_IMAGE_FORMAT,
)
from helpers.checks import cooldown, premium_command, user_check
from helpers.converters import HexOrRGB, colour_option, rgb_to_hex, user_option
from helpers.errors import ImproperArgument
from helpers.image import get_base_img, save_discord_static_img
from helpers.ui import BaseView, ScrollView
from helpers.user import get_pacer_display, get_theme_display
from helpers.utils import copy_doc, invoke_completion, invoke_slash_command
from static import themes


async def _get_theme_preview_file(bot, theme):
    raw_quote = "Lorem ipsum dolor sit amet, consectetur adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Lorem ipsum dolor sit amet consectetur adipiscing. Id cursus metus aliquam eleifend mi in nulla posuere."

    base_img = await get_base_img(bot, raw_quote, DEFAULT_WRAP, theme)

    return save_discord_static_img(base_img, "preview")


# Formula from: https://gist.github.com/ryancat/9972419b2a78f329ce3aebb7f1a09152
def _get_colour_perceptual_distance(c1, c2):
    """Calculates perceptual distance between two colours"""
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


def _get_difficulty_choices(name):
    """Finds language difficulty options from selected language"""
    return word_list.languages.get(name, [])


class EquipSelect(discord.ui.Select):
    def __init__(self, ctx: Context, badges):
        none_option = discord.SelectOption(label="None", value="no")

        super().__init__(
            placeholder="Select a badge to equip...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=b.get_name(b.badge_id),
                    emoji=None
                    if b.raw is None
                    else discord.PartialEmoji.from_str(b.raw),
                    value=b.badge_id,
                )
                for b in badges
            ]
            + [none_option],
            row=1,
        )
        self.ctx = ctx

    async def callback(self, interaction):
        option = self.values[0]
        self.disabled = True

        option_name = next((s.label for s in self.options if s.value == option), None)

        embed = self.ctx.embed(
            title=f"{icons.success} {option_name} Badge Equipped",
            add_footer=False,
        )

        await interaction.response.edit_message(embed=embed, view=None)

        user = await self.ctx.bot.mongo.fetch_user(self.ctx.author)

        if option is None:
            user.status = ""
        else:
            user.status = option

        await self.ctx.bot.mongo.replace_user_data(user, self.ctx.author)


class EquipView(ScrollView):
    def __init__(self, ctx: Context, user):
        self.user = user

        self.select_view = None

        super().__init__(ctx, iter=self.user.badge_objs, per_page=24, row=2)

    async def update_buttons(self):
        self.update_select_view()
        return await super().update_buttons()

    def update_select_view(self):
        if self.select_view is not None:
            self.remove_item(self.select_view)

        self.select_view = EquipSelect(self.ctx, self.items)
        self.add_item(self.select_view)


class ThemeSelect(discord.ui.Select):
    def __init__(self, ctx: Context):
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

    async def callback(self, interaction):
        option = self.values[0]

        self.disabled = True

        theme_value = themes.default[option]["colours"]

        embed = self.ctx.custom_embed(
            title="Theme Selected",
            color=int(theme_value[1].replace("#", "0x"), 16),
            add_footer=False,
        )

        file = await _get_theme_preview_file(self.ctx.bot, theme_value)

        embed.set_image(url=f"attachment://preview.{STATIC_IMAGE_FORMAT}")

        await interaction.response.edit_message(embed=embed, file=file, view=None)

        user = await self.ctx.bot.mongo.fetch_user(self.ctx.author)

        user.theme = theme_value

        await self.ctx.bot.mongo.replace_user_data(user, self.ctx.author)

        invoke_completion(self.ctx)


class Customization(commands.Cog):
    """Customization commands"""

    emoji = "\N{GEAR}"
    order = 3

    def __init__(self, bot: WordPractice):
        self.bot = bot

    # Groups
    theme_group = SlashCommandGroup("theme", "Change the typing test theme")
    pacer_group = SlashCommandGroup("pacer", "Set a pacer for your typing test")

    # Arguments
    difficulty_option = discord.option(
        "difficulty",
        str,
        description="Choose a language difficulty",
        autocomplete=discord.utils.basic_autocomplete(
            lambda ctx: _get_difficulty_choices(ctx.options.get("name"))
        ),
    )
    language_option = discord.option(
        "name", str, description="Choose a language", choices=word_list.languages.keys()
    )

    formatted_pacer_planes = [p.capitalize() for p in PACER_PLANES]

    @theme_group.command(name="custom")
    @premium_command()
    @cooldown(8, 3)
    @colour_option("background")
    @colour_option("text")
    async def theme_custom(self, ctx: Context, background, text):
        """Create a custom theme for your typing test"""

        distance = _get_colour_perceptual_distance(background, text)

        colours = [rgb_to_hex(*background), rgb_to_hex(*text)]

        embed_clr = int(colours[1].replace("#", "0x"), 16)

        # Warning if the perceptual distance is too low
        if distance < 40:
            embed = ctx.custom_embed(
                title=f"{icons.caution} Custom Theme Applied",
                description="Low colour contrast detected!",
                color=embed_clr,
                add_footer=False,
            )
        else:
            embed = ctx.custom_embed(
                title=f"{icons.success} Custom Theme Applied",
                color=embed_clr,
                add_footer=False,
            )

        file = await _get_theme_preview_file(self.bot, colours)

        embed.set_image(url=f"attachment://preview.{STATIC_IMAGE_FORMAT}")

        await ctx.respond(embed=embed, file=file)

        user = ctx.initial_user

        user.theme = colours

        await self.bot.mongo.replace_user_data(user, ctx.author)

    @theme_group.command()
    @cooldown(8, 3)
    async def premade(self, ctx: Context):
        """Choose a premade theme for your typing test"""

        await self.handle_premade_theme(ctx)

    async def handle_premade_theme(self, ctx):
        view = BaseView(ctx)
        view.add_item(ThemeSelect(ctx))

        await ctx.respond(content="** **", view=view)

    @commands.group(hidden=True, invoke_without_command=True)
    @cooldown(8, 3)
    @copy_doc(premade)
    async def theme(self, ctx: Context):
        await invoke_slash_command(self.premade, self, ctx)

    @theme.command(name="custom")
    @cooldown(8, 3)
    @premium_command()
    @copy_doc(theme_custom)
    async def _theme_custom(self, ctx: Context, background, text):
        converter = HexOrRGB()

        background = await converter.convert(ctx, background)
        text = await converter.convert(ctx, text)

        await invoke_slash_command(self.theme_custom, self, ctx, background, text)

    @theme.command(name="premade")
    @cooldown(8, 3)
    @copy_doc(premade)
    async def _premade(self, ctx: Context):
        await invoke_slash_command(self.premade, self, ctx)

    @bridge.bridge_command()
    @cooldown(8, 3)
    @difficulty_option
    @language_option
    async def language(self, ctx: Context, name: str, difficulty: str):
        """Choose a language for your typing test"""

        # Checking if difficulty is valid
        if difficulty not in (choices := _get_difficulty_choices(name)):
            raise ImproperArgument(
                "That is not a valid difficulty", options=list(choices.keys())
            )

        embed = ctx.embed(
            title=f"{icons.success} `{name.capitalize()} {difficulty.capitalize()}` is now your set language!",
            add_footer=False,
        )

        await ctx.respond(embed=embed)

        user = ctx.initial_user

        user.language = name
        user.level = difficulty

        await self.bot.mongo.replace_user_data(user, ctx.author)

    async def handle_update_pacer_speed(self, ctx: Context, name, value):
        embed = ctx.embed(
            title=f"{icons.success} Updated pacer speed to {name}", add_footer=False
        )
        await ctx.respond(embed=embed)

        user = ctx.initial_user

        user.pacer_speed = value

        await self.bot.mongo.replace_user_data(user, ctx.author)

    @pacer_group.command()
    @cooldown(8, 3)
    async def style(
        self,
        ctx: Context,
        plane: Option(
            str,
            "Pick a style for your pacer",
            choices=formatted_pacer_planes,
            required=True,
        ),
    ):
        """Change the style of your pacer"""
        index = PACER_PLANES.index(plane.lower())

        embed = ctx.embed(
            title=f"{icons.success} Updated pacer style to {self.formatted_pacer_planes[index]}",
            add_footer=False,
        )

        await ctx.respond(embed=embed)

        user = ctx.initial_user

        user.pacer_type = index

        await self.bot.mongo.replace_user_data(user, ctx.author)

    @pacer_group.command()
    @cooldown(8, 3)
    async def pb(self, ctx: Context):
        """Set your typing test pacer to your personal best"""
        await self.handle_update_pacer_speed(ctx, "Personal Best", "pb")

    @pacer_group.command()
    @cooldown(8, 3)
    async def average(self, ctx: Context):
        """Set your typing test pacer to your average speed"""
        await self.handle_update_pacer_speed(ctx, "Average", "avg")

    @pacer_group.command()
    @cooldown(8, 3)
    async def off(self, ctx: Context):
        """Turn off your typing test pacer"""
        await self.handle_update_pacer_speed(ctx, "Off", "")

    @pacer_group.command(name="custom")
    @cooldown(8, 3)
    async def pacer_custom(
        self,
        ctx: Context,
        speed: Option(
            int,
            f"Choose a pacer speed from {MIN_PACER_SPEED}-300",
            required=True,
        ),
    ):
        """Set your typing test pacer to a custom speed"""

        if speed not in range(MIN_PACER_SPEED, 301):
            raise commands.BadArgument(
                f"Pacer speed must be between {MIN_PACER_SPEED} and 300"
            )

        await self.handle_update_pacer_speed(ctx, f"{speed} wpm", str(speed))

    @commands.group(hidden=True, case_insensitive=True, invoke_without_command=True)
    @cooldown(8, 3)
    async def pacer(self, ctx: Context, speed: int):
        await invoke_slash_command(self.pacer_custom, self, ctx, speed)

    @pacer.command(name="custom")
    @cooldown(8, 3)
    @copy_doc(pacer_custom)
    async def _pacer_custom(self, ctx: Context, speed: int):
        await invoke_slash_command(self.pacer_custom, self, ctx, speed)

    @pacer.command(name="style")
    @cooldown(8, 3)
    @copy_doc(style)
    async def _style(self, ctx: Context, plane: str):

        if plane.lower() not in PACER_PLANES:
            raise commands.BadArgument(
                "Pacer plane must be: " + ", ".join(self.formatted_pacer_planes)
            )

        await invoke_slash_command(self.style, self, ctx, plane)

    @pacer.command(name="pb")
    @cooldown(8, 3)
    @copy_doc(pb)
    async def _pb(self, ctx: Context):
        await invoke_slash_command(self.pb, self, ctx)

    @pacer.command(name="average")
    @cooldown(8, 3)
    @copy_doc(average)
    async def _average(self, ctx: Context):
        await invoke_slash_command(self.average, self, ctx)

    @pacer.command(name="off")
    @cooldown(8, 3)
    @copy_doc(off)
    async def _off(self, ctx: Context):
        await invoke_slash_command(self.off, self, ctx)

    @bridge.bridge_command()
    @cooldown(8, 3)
    async def equip(self, ctx: Context):
        """Equip a badge that you own"""
        user = ctx.initial_user

        if len(user.badges) == 0:
            embed = ctx.error_embed(
                title=f"{icons.caution} You don't have any badges!",
                description="Earn badges through achievements and monthly seasons",
            )
            return await ctx.respond(embed=embed)

        view = EquipView(ctx, user)

        await view.start()

    @commands.user_command(name="Typing Settings")
    @cooldown(5, 2)
    async def settings_user(self, ctx: Context, member: discord.Member):
        await self.handle_settings_cmd(ctx, member)

    @bridge.bridge_command()
    @cooldown(5, 2)
    @user_option
    async def settings(self, ctx: Context, *, user: discord.User = None):
        """View user settings"""
        await self.handle_settings_cmd(ctx, user)

    async def handle_settings_cmd(self, ctx, user):

        user = await user_check(ctx, user)

        embed = ctx.embed(
            title=f"{user.display_name} | User Settings",
        )

        pacer_name = get_pacer_display(user.pacer_type, user.pacer_speed)

        theme_name, theme_icon = get_theme_display(user.theme)

        embed.add_field(
            name=":paintbrush: Theme",
            value=f"{theme_icon} {theme_name} (`{user.theme[0]}`, `{user.theme[1]}`)"
            + (
                ""
                if ctx.initial_user.is_premium
                else f"\n**[Premium Members]({PREMIUM_LINK})** can unlock custom themes!"
            ),
            inline=False,
        )

        embed.add_field(
            name=f"** **\n{icons.language} Language",
            value=f"{user.language.capitalize()} ({user.level.capitalize()})",
            inline=False,
        )

        embed.add_field(
            name=f"** **\n{icons.pacer} Pacer", value=f"{pacer_name}", inline=False
        )

        embed.set_thumbnail(url="https://i.imgur.com/2vUD4NF.png")

        await ctx.respond(embed=embed)


def setup(bot: WordPractice):
    bot.add_cog(Customization(bot))
