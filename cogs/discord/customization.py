import math

import discord
from discord.commands import Option, SlashCommandGroup
from discord.ext import commands

import icons
import word_list
from constants import DEFAULT_WRAP, MIN_PACER_SPEED, PREMIUM_LINK, STATIC_IMAGE_FORMAT
from helpers.checks import cooldown, premium_command, user_check
from helpers.converters import opt_user, rgb_to_hex, rqd_colour
from helpers.errors import ImproperArgument
from helpers.image import get_base_img, save_discord_static_img
from helpers.ui import BaseView
from helpers.user import get_pacer_display, get_theme_display
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
    def __init__(self, ctx, user):
        none_option = discord.SelectOption(label="None", value="no")

        super().__init__(
            placeholder="Select a badge to equip...",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=name.capitalize(),
                    emoji=None if icon is None else discord.PartialEmoji.from_str(icon),
                    value=name,
                )
                for name, icon in zip(user.badges, user.badge_emojis)
            ]
            + [none_option],
            row=1,
        )
        self.ctx = ctx

    async def callback(self, interaction):
        option = self.values[0]
        self.disabled = True

        option_name = option.capitalize()

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


class Customization(commands.Cog):
    """Customization commands"""

    emoji = "\N{GEAR}"
    order = 3

    def __init__(self, bot):
        self.bot = bot

    theme_group = SlashCommandGroup("theme", "Change the typing test theme")
    pacer_group = SlashCommandGroup("pacer", "Set a pacer for your typing test")

    @premium_command()
    @cooldown(8, 3)
    @theme_group.command()
    async def custom(self, ctx, background: rqd_colour(), text: rqd_colour()):
        """Create a custom theme for your typing test"""

        distance = _get_colour_perceptual_distance(background, text)

        colours = [rgb_to_hex(*background), rgb_to_hex(*text)]

        embed_clr = int(colours[1].replace("#", "0x"), 16)

        # Warning if the perceptual distance is too low
        if distance < 45:
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
        view = BaseView(ctx)
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
                lambda ctx: _get_difficulty_choices(ctx.options.get("name"))
            ),
        ),
    ):
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
            choices=["Horizontal", "Vertical"],
            required=True,
        ),
    ):
        """Change the style of your pacer"""
        update = int(plane == "Vertical")

        embed = ctx.embed(
            title=f"{icons.success} Updated pacer style to {plane}",
            add_footer=False,
        )

        await ctx.respond(embed=embed)

        user = ctx.initial_user

        user.pacer_type = update

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
    @pacer_group.command()
    async def custom(
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
    @commands.slash_command()
    async def equip(self, ctx):
        """Equip a badge that you own"""
        user = ctx.initial_user

        if len(user.badges) == 0:
            embed = ctx.error_embed(
                title=f"{icons.caution} You don't have any badges!",
                description="Earn badges through achievements and monthly seasons",
            )
            return await ctx.respond(embed=embed)

        view = BaseView(ctx)

        view.add_item(EquipSelect(ctx, user))

        await ctx.respond(content="** **", view=view)

    @cooldown(5, 2)
    @commands.user_command(name="Typing Settings")
    async def settings_user(self, ctx, member: discord.Member):
        await self.handle_settings_cmd(ctx, member)

    @cooldown(5, 2)
    @commands.slash_command()
    async def settings(self, ctx, user: opt_user()):
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
