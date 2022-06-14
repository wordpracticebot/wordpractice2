import math

import discord
from discord.commands import Option, SlashCommandGroup
from discord.ext import bridge, commands

import icons
import word_list
from constants import (
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
    raw_quote = "This is a preview of your theme. Thomas the chatbot was walking down the street with an ice cream cone. He dropped the cone on the ground and was sad. The End."

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
    def __init__(self, ctx, badges):
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
    def __init__(self, ctx, user):

        self.total_badges = len(user.badges)

        page_amt = math.ceil(self.total_badges / 24)

        super().__init__(ctx, page_amt, row=2)

        self.user = user

        self.select_view = None

    async def update_buttons(self):
        self.update_select_view()
        return await super().update_buttons()

    async def create_page(self):
        ...

    def update_select_view(self):
        if self.select_view is not None:
            self.remove_item(self.select_view)

        start_page = self.page * 24
        end_page = min((self.page + 1) * 24, self.total_badges)

        self.select_view = EquipSelect(
            self.ctx, self.user.badge_objs[start_page:end_page]
        )
        self.add_item(self.select_view)


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

    def __init__(self, bot):
        self.bot = bot

    # Groups
    theme_group = SlashCommandGroup("theme", "Change the typing test theme")
    pacer_group = SlashCommandGroup("pacer", "Set a pacer for your typing test")

    # Arguments
    difficulty_option = discord.option(
        "difficulty",
        str,
        autocomplete=discord.utils.basic_autocomplete(
            lambda ctx: _get_difficulty_choices(ctx.options.get("name"))
        ),
    )
    language_option = discord.option(
        "name", str, desc="Choose a language", choices=word_list.languages.keys()
    )

    formatted_pacer_planes = [p.capitalize() for p in PACER_PLANES]

    @premium_command()
    @cooldown(8, 3)
    @theme_group.command(name="custom")
    @colour_option("background")
    @colour_option("text")
    async def theme_custom(self, ctx, background, text):
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

    @cooldown(8, 3)
    @theme_group.command()
    async def premade(self, ctx):
        """Choose a premade theme for your typing test"""

        await self.handle_premade_theme(ctx)

    async def handle_premade_theme(self, ctx):
        view = BaseView(ctx)
        view.add_item(ThemeSelect(ctx))

        await ctx.respond(content="** **", view=view)

    @cooldown(8, 3)
    @commands.group(hidden=True, invoke_without_command=True)
    @copy_doc(premade)
    async def theme(self, ctx):
        await invoke_slash_command(self.premade, self, ctx)

    @premium_command()
    @cooldown(8, 3)
    @theme.command(name="custom")
    @copy_doc(theme_custom)
    async def _theme_custom(self, ctx, background, text):
        converter = HexOrRGB()

        background = await converter.convert(ctx, background)
        text = await converter.convert(ctx, text)

        await invoke_slash_command(self.theme_custom, self, ctx, background, text)

    @cooldown(8, 3)
    @theme.command(name="premade")
    @copy_doc(premade)
    async def _premade(self, ctx):
        await invoke_slash_command(self.premade, self, ctx)

    @cooldown(8, 3)
    @bridge.bridge_command()
    @difficulty_option
    @language_option
    async def language(self, ctx, name: str, difficulty: str):
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

    async def handle_update_pacer_speed(self, ctx, name, value):
        embed = ctx.embed(
            title=f"{icons.success} Updated pacer speed to {name}", add_footer=False
        )
        await ctx.respond(embed=embed)

        user = ctx.initial_user

        user.pacer_speed = value

        await self.bot.mongo.replace_user_data(user, ctx.author)

    @cooldown(8, 3)
    @pacer_group.command()
    async def style(
        self,
        ctx,
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

    @cooldown(8, 3)
    @pacer_group.command()
    async def pb(self, ctx):
        """Set your typing test pacer to your personal best"""
        await self.handle_update_pacer_speed(ctx, "Personal Best", "pb")

    @cooldown(8, 3)
    @pacer_group.command()
    async def average(self, ctx):
        """Set your typing test pacer to your average speed"""
        await self.handle_update_pacer_speed(ctx, "Average", "avg")

    @cooldown(8, 3)
    @pacer_group.command()
    async def off(self, ctx):
        """Turn off your typing test pacer"""
        await self.handle_update_pacer_speed(ctx, "Off", "")

    @cooldown(8, 3)
    @pacer_group.command(name="custom")
    async def pacer_custom(
        self,
        ctx,
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

    @cooldown(8, 3)
    @commands.group(hidden=True, case_insensitive=True, invoke_without_command=True)
    async def pacer(self, ctx, speed: int):
        await invoke_slash_command(self.pacer_custom, self, ctx, speed)

    @cooldown(8, 3)
    @pacer.command(name="custom")
    @copy_doc(pacer_custom)
    async def _pacer_custom(self, ctx, speed: int):
        await invoke_slash_command(self.pacer_custom, self, ctx, speed)

    @cooldown(8, 3)
    @pacer.command(name="style")
    @copy_doc(style)
    async def _style(self, ctx, plane: str):

        if plane.lower() not in PACER_PLANES:
            raise commands.BadArgument(
                "Pacer plane must be: " + ", ".join(self.formatted_pacer_planes)
            )

        await invoke_slash_command(self.style, self, ctx, plane)

    @cooldown(8, 3)
    @pacer.command(name="pb")
    @copy_doc(pb)
    async def _pb(self, ctx):
        await invoke_slash_command(self.pb, self, ctx)

    @cooldown(8, 3)
    @pacer.command(name="average")
    @copy_doc(average)
    async def _average(self, ctx):
        await invoke_slash_command(self.average, self, ctx)

    @cooldown(8, 3)
    @pacer.command(name="off")
    @copy_doc(off)
    async def _off(self, ctx):
        await invoke_slash_command(self.off, self, ctx)

    @cooldown(8, 3)
    @bridge.bridge_command()
    async def equip(self, ctx):
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

    @cooldown(5, 2)
    @commands.user_command(name="Typing Settings")
    async def settings_user(self, ctx, member: discord.Member):
        await self.handle_settings_cmd(ctx, member)

    @cooldown(5, 2)
    @bridge.bridge_command()
    @user_option
    async def settings(self, ctx, user: discord.User = None):
        """View user settings"""
        await self.handle_settings_cmd(ctx, user)

    async def handle_settings_cmd(self, ctx, user):

        user = await user_check(ctx, user)

        author_data = await self.bot.mongo.fetch_user(ctx.author)

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
                if author_data.is_premium
                else f"\n**[Donators]({PREMIUM_LINK})** can unlock custom themes!"
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


def setup(bot):
    bot.add_cog(Customization(bot))
