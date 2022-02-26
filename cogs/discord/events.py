import copy
import time
from datetime import datetime
from io import BytesIO

import discord
from discord.ext import commands
from discord.ext.commands import errors
from discord.utils import escape_markdown
from PIL import ImageDraw

import icons
from achievements import check_all
from constants import ACHIEVEMENTS_SHOWN, SUPPORT_SERVER_INVITE
from helpers.errors import ImproperArgument
from helpers.ui import create_link_view
from helpers.user import get_user_cmds_run
from helpers.utils import format_slash_command
from static.assets import achievement_base, uni_sans_heavy


# TODO: add icons to achievement image
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

        command = format_slash_command(ctx.command)

        name = escape_markdown(str(ctx.author))
        guild = escape_markdown(str(ctx.guild))

        embed = ctx.default_embed(
            description=(
                f"**User:** {name} ({ctx.author.id})\n"
                f"**Server:** {guild} ({ctx.guild.id})\n"
                f"**Command:** {command}\n"
                f"**Timestamp:** <t:{timestamp}:R>"
            ),
        )

        await self.bot.cmd_wh.send(embed=embed)

    @staticmethod
    async def send_basic_error(ctx, title, desc):
        embed = ctx.error_embed(title=f"{icons.caution} {title}", description=desc)

        await ctx.respond(embed=embed)

    @commands.Cog.listener()
    async def on_application_command_error(self, ctx, error):
        if isinstance(error, discord.commands.CheckFailure):
            return await self.handle_check_failure(ctx, error)

        error = error.original

        if isinstance(error, errors.UserInputError):
            await self.handle_user_input_error(ctx, error)

        else:
            await self.handle_unexpected_error(ctx, error)

    async def handle_user_input_error(self, ctx, error):
        if isinstance(error, errors.BadArgument):
            message = str(error)

            if isinstance(error, ImproperArgument) and error.options:
                options = " ".join(f"`{o}`" for o in error.options)
                message += f"\n\n**Did you mean?**\n{options}"

            await self.send_basic_error(ctx, "Invalid Argument", message)

        else:
            await self.send_basic_error(
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
                await self.send_basic_error(
                    ctx,
                    "Permission Error",
                    "I do not have the correct server permissons",
                )
            except:  # bare exception :eyes:
                pass

    async def handle_unexpected_error(self, ctx, error):
        view = create_link_view({"Support Server": SUPPORT_SERVER_INVITE})

        embed = ctx.error_embed(
            title=f"{icons.danger} Unexpected Error",
            description="Report this through our support server so we can fix it.",
        )

        await ctx.respond(embed=embed, view=view)

        timestamp = int(time.time())

        command = format_slash_command(ctx.command)

        name = escape_markdown(str(ctx.author))
        guild = escape_markdown(str(ctx.guild))

        embed = ctx.error_embed(
            title="Unexpected Error",
            description=(
                f"**User:** {name} ({ctx.author.id})\n"
                f"**Server:** {guild} ({ctx.guild.id})\n"
                f"**Command:** {command}\n"
                f"**Timestamp:** <t:{timestamp}:R>"
            ),
        )

        await self.bot.log_the_error(embed, error)

    @commands.Cog.listener()
    async def on_application_command(self, ctx):
        # Logging the interaction
        await self.log_interaction(ctx)

    def get_files_from_earned(self, earned):
        files = []
        extra = 0

        for m in earned.values():
            raw_names, _ = zip(*m)
            a, t = m[-1]

            if len(files) < ACHIEVEMENTS_SHOWN:
                if t is not None and raw_names.count(a) > 1:
                    a += f" ({t + 1})"

                image = generate_achievement_image(a)

                files.append(image)
            else:
                extra += 1

        return files, extra

    @commands.Cog.listener()
    async def on_application_command_completion(self, ctx):
        user = await self.bot.mongo.fetch_user(ctx.author, create=True)

        new_user = copy.deepcopy(user)

        now = datetime.utcnow()

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

        a_earned = {}
        done_checking = False

        while done_checking is False:
            new_a = False
            # Looping through all the finished achievements
            for (a, changer), count, identifier in check_all(new_user):

                a_earned[identifier] = a_earned.get(identifier, []) + [(a.name, count)]
                new_a = True

                # Adding achievemnt to document
                insert_count = 0 if count is None else count
                current = new_user.achievements.get(a.name, [])
                current.insert(insert_count, datetime.utcnow())

                new_user.achievements[a.name] = current

                if a.reward is None:
                    continue

                # Checking if the state doesn't need to be updated
                if changer == True:
                    continue

                # Updating the new user state
                new_user = changer(new_user)

            # Continues checking until no new achievements are given in a round (allows chaining achievements)
            if new_a is False:
                done_checking = True

        # Updating the user's executed commands

        cmd_name = format_slash_command(ctx.command)

        cmds = get_user_cmds_run(self.bot, new_user)

        if cmd_name not in cmds:
            new_cache_cmds = self.bot.cmds_run.get(ctx.author.id, set()) | {cmd_name}

            # Updating in database if the user document was going to be updated anyways or there are 3 or more commands not saved in database
            if user.to_mongo() != new_user.to_mongo() or len(new_cache_cmds) >= 3:
                new_user.cmds_run = list(set(new_user.cmds_run) | new_cache_cmds)

            else:
                self.bot.cmds_run[ctx.author.id] = new_cache_cmds

        if user.to_mongo() != (user_data := new_user.to_mongo()):
            # Checking if neaw achievements have been added
            if user.achievements != new_user.achievements:
                files, extra = self.get_files_from_earned(a_earned)

                if extra:
                    await ctx.respond(
                        f"and {extra} more...",
                        files=files,
                        ephemeral=True,
                    )
                else:
                    await ctx.respond(files=files, ephemeral=True)

            # Replacing the user data with the new state
            # TODO: potentially dangerous, find better way without updating all fields
            await self.bot.mongo.replace_user_data(ctx.author, user_data)


def setup(bot):
    bot.add_cog(Events(bot))
