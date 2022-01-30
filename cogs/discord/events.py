import copy
import time
import traceback
from datetime import datetime, timedelta
from io import BytesIO

import discord
from discord.ext import commands
from discord.ext.commands import errors
from PIL import ImageDraw

from achievements import check_all
from constants import ACHIEVEMENTS_SHOWN, SUPPORT_SERVER
from helpers.errors import ImproperArgument
from helpers.ui import create_link_view
from static.assets import achievement_base, uni_sans_heavy


def generate_achievement_image(name):
    img = achievement_base.copy()

    draw = ImageDraw.Draw(img)
    draw.text((240, 110), name, font=uni_sans_heavy)

    buffer = BytesIO()
    img.save(buffer, "png")
    buffer.seek(0)

    return discord.File(fp=buffer, filename="image.png")


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def log_interaction(self, ctx):
        # Logging the interaction

        timestamp = int(time.time())

        options = (
            " ".join(f"[{o.name}]" for o in ctx.command.options)
            if ctx.command.options
            else ""
        )

        embed = ctx.embed(
            description=(
                f"**User:** {ctx.author} ({ctx.author.id})\n"
                f"**Server:** {ctx.guild} ({ctx.guild.id})\n"
                f"**Command:** {ctx.command.name} {options}\n"
                f"**Timestamp:** <t:{timestamp}:R>"
            ),
            add_footer=False,
        )

        await self.bot.cmd_wh.send(embed=embed)

    @staticmethod
    async def send_error(ctx, title, desc, view=None):
        embed = ctx.error_embed(title=title, description=desc)

        if view is None:
            await ctx.respond(embed=embed)
        else:
            await ctx.respond(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_application_command_error(self, ctx, error):
        if isinstance(error, errors.UserInputError):
            await self.handle_user_input_error(ctx, error)

        elif isinstance(error, discord.commands.CheckFailure):
            await self.handle_check_failure(ctx, error)

        elif isinstance(error, errors.MaxConcurrencyReached):
            return

        else:
            await self.handle_unexpected_error(ctx, error)

    async def handle_user_input_error(self, ctx, error):
        if isinstance(error, errors.BadArgument):
            message = str(error)

            if isinstance(error, ImproperArgument) and error.options:
                options = " ".join(f"`{o}`" for o in error.options)
                message += f"\n\n**Did you mean?**\n{options}"

            await self.send_error(ctx, "Invalid Argument", message)

        else:
            await self.send_error(
                ctx,
                "Invalid Input",
                (
                    "Your input is malformed"
                    f"Type `{ctx.prefix}help` for a list of commands"
                ),
            )

    async def handle_check_failure(self, ctx, error):
        if isinstance(
            error,
            (
                errors.BotMissingPermissions,
                errors.BotMissingRole,
                errors.BotMissingAnyRole,
            ),
        ):
            try:
                await self.send_error(
                    ctx,
                    "Permission Error",
                    "I do not have the correct server permissons",
                )
            except:  # bare exception :eyes:
                pass

    async def handle_unexpected_error(self, ctx, error):
        view = create_link_view({"Support Server": SUPPORT_SERVER})

        await self.send_error(
            ctx,
            "Unexpected Error",
            "Please report this through our support server so we can fix it.",
            view,
        )

        timestamp = int(time.time())

        options = (
            " ".join(f"[{o.name}]" for o in ctx.command.options)
            if ctx.command.options
            else ""
        )

        embed = ctx.error_embed(
            title="Unexpected Error",
            description=(
                f"**User:** {ctx.author} ({ctx.author.id})\n"
                f"**Server:** {ctx.guild} ({ctx.guild.id})\n"
                f"**Command:** {ctx.command.name} {options}\n"
                f"**Timestamp:** <t:{timestamp}:R>"
            ),
            add_footer=False,
        )

        msg = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )

        buffer = BytesIO(msg.encode("utf-8"))
        file = discord.File(buffer, filename="text.txt")

        await self.bot.impt_wh.send(embed=embed, file=file)

        print(msg)

    @commands.Cog.listener()
    async def on_application_command(self, ctx):
        # Logging the interaction
        await self.log_interaction(ctx)

    @commands.Cog.listener()
    async def on_application_command_completion(self, ctx):
        user = await self.bot.mongo.fetch_user(ctx.author, create=True)
        new_user = copy.deepcopy(user)

        now = datetime.now()

        days_between = (
            now - new_user.last_streak.replace(hour=now.hour, minute=now.minute)
        ).days

        # Updating the user's playing streak

        if days_between > 1:
            new_user.streak = 1
        elif days_between == 1:
            new_user.streak += 1
            if new_user.streak > new_user.highest_streak:
                new_user.highest_streak = new_user.streak

        if days_between > 0:
            new_user.last_streak = now

        names = []
        done_checking = False

        while done_checking is False:
            new_names = []

            # Looping through all the finished achievements
            for a, changer in check_all(new_user):
                new_names.append(a.name)

                # adding achievemnt to document
                new_user.achievements[a.name] = datetime.now()

                if a.reward is None:
                    continue

                # Checking if the state doesn't need to be updated
                if changer == True:
                    continue

                # Updating the new user state
                new_user = changer(new_user)

            if new_names != []:
                names += new_names
            else:
                done_checking = True

        if user.to_mongo() != (user_data := new_user.to_mongo()):
            files = [generate_achievement_image(n) for n in names[:ACHIEVEMENTS_SHOWN]]

            if len(names) > ACHIEVEMENTS_SHOWN:
                await ctx.respond(
                    f"and {len(names) - ACHIEVEMENTS_SHOWN} more...",
                    files=files,
                    ephemeral=True,
                )
            else:
                await ctx.respond(files=files, ephemeral=True)

            # Replacing the user data with the new state
            await self.bot.mongo.replace_user_data(ctx.author, user_data)


def setup(bot):
    bot.add_cog(Events(bot))
