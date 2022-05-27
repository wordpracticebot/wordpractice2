import copy
from datetime import datetime

import discord
from discord.ext import commands
from discord.ext.commands import errors
from PIL import ImageDraw

import icons
from challenges.achievements import check_all
from challenges.daily import get_daily_challenges
from challenges.rewards import group_rewards
from challenges.season import check_season_rewards
from constants import ACHIEVEMENTS_SHOWN, SUPPORT_SERVER_INVITE
from helpers.errors import ImproperArgument, OnGoingTest
from helpers.image import save_img_as_discord_png
from helpers.ui import create_link_view, get_log_embed
from helpers.user import get_user_cmds_run
from helpers.utils import format_slash_command
from static.assets import achievement_base, uni_sans_heavy


def _generate_achievement_image(name, icon):
    img = achievement_base.copy()

    if icon is not None:
        img_icon = icon.copy().resize((95, 95))
        img.paste(img_icon, (52, 52), img_icon)

    draw = ImageDraw.Draw(img)
    draw.text((240, 110), name, font=uni_sans_heavy)

    return save_img_as_discord_png(img, "achievement")


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    async def log_interaction(self, ctx):
        # Logging the interaction

        command = format_slash_command(ctx.command)

        embed = get_log_embed(ctx, title=None, additional=f"**Command:** {command}")

        await self.bot.cmd_wh.send(embed=embed)

    @staticmethod
    async def send_basic_error(
        ctx, *, title, desc=None, severe=False, ephemeral=False, view=None
    ):
        added = f"{icons.danger} `ERROR!`" if severe else icons.caution

        embed = ctx.error_embed(title=f"{added} {title}", description=desc)

        await ctx.respond(embed=embed, ephemeral=ephemeral, view=view)

    @commands.Cog.listener()
    async def on_application_command_error(self, ctx, error):
        if isinstance(error, (discord.errors.CheckFailure, commands.CheckFailure)):

            if isinstance(error, errors.BotMissingPermissions):
                await self.send_basic_error(
                    ctx, title="Bot Missing Permissions", severe=True
                )

            return self.bot.active_end(ctx.author.id)

        if isinstance(error, OnGoingTest):
            return await self.bot.handle_ongoing_test_error(ctx.respond)

        self.bot.active_end(ctx.author.id)

        if isinstance(error, discord.errors.Forbidden):
            try:
                await self.send_basic_error(
                    ctx,
                    title="Permission Error",
                    desc="I am missing the correct permissions",
                )
            except Exception:
                pass

            return

        if isinstance(error, errors.UserInputError):
            return await self.handle_user_input_error(ctx, error)

        await self.handle_unexpected_error(ctx, error)

    async def handle_user_input_error(self, ctx, error):
        if isinstance(error, errors.BadArgument):
            message = str(error)

            if isinstance(error, ImproperArgument) and error.options:
                options = " ".join(f"`{o}`" for o in error.options)
                message += f"\n\n**Did you mean?**\n{options}"

            return await self.send_basic_error(
                ctx, title="Invalid Argument", desc=message, severe=True
            )

        await self.send_basic_error(
            ctx,
            title="Invalid Input",
            desc=(
                "Your input is malformed"
                f"Type `{ctx.prefix}help` for a list of commands"
            ),
        )

    async def handle_unexpected_error(self, ctx, error):
        view = create_link_view({"Support Server": SUPPORT_SERVER_INVITE})

        await self.send_basic_error(
            ctx,
            title="Unexpected Error",
            desc="> Report this through our support server so we can fix it.",
            view=view,
            severe=True,
        )

        command = format_slash_command(ctx.command)

        embed = get_log_embed(
            ctx,
            title="Unexpected Error",
            additional=f"**Command:** {command}",
            error=True,
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
            a, t, c = m[-1]

            name = a.name

            if len(files) < ACHIEVEMENTS_SHOWN:
                if t is not None:
                    name += f" ({t + 1})"

                image = _generate_achievement_image(name, c.icon)

                files.append(image)
            else:
                extra += 1

        return files, extra

    @commands.Cog.listener()
    async def on_application_command_completion(self, ctx):

        if ctx.no_completion:
            return

        user = await self.bot.mongo.fetch_user(ctx.author, create=True)

        new_user = copy.deepcopy(user)

        now = datetime.utcnow()

        days_between = (now - new_user.last_streak).days

        # Updating the user's playing streak

        if days_between > 1:
            new_user.streak = 1

        elif days_between == 1:
            new_user.streak += 1
            if new_user.streak > new_user.highest_streak:
                new_user.highest_streak = new_user.streak

        if days_between >= 1:
            new_user.last_streak = now

        # Achievements

        a_earned = {}
        done_checking = False

        while done_checking is False:
            new_a = False
            # Looping through all the finished achievements
            async for a, count, cv, identifier in check_all(ctx, new_user):
                a_earned[identifier] = a_earned.get(identifier, []) + [(a, count, cv)]
                new_a = True

                # Adding achievemnt to document
                insert_count = 0 if count is None else count
                current = new_user.achievements.get(a.name, [])

                current.insert(insert_count, datetime.utcnow())

                new_user.achievements[a.name] = current

                if a.reward is None:
                    continue

                # Checking if the state doesn't need to be updated
                if a.changer is None:
                    continue

                # Updating the new user state
                new_user = a.changer(new_user)

            # Continues checking until no new achievements are given in a round (allows chaining achievements)
            if new_a is False:
                done_checking = True

        # Daily challenges

        challenges, daily_reward = get_daily_challenges()

        new_user.daily_completion = [
            (n and c.immutable) or await c.is_completed(ctx, new_user)
            for n, c in zip(new_user.daily_completion, challenges)
        ]

        new_daily_completion = (
            user.is_daily_complete is False and new_user.is_daily_complete
        )

        if new_daily_completion:
            new_user = daily_reward.changer(new_user)

        # Season rewards

        season_rewards = [i async for i in check_season_rewards(ctx.bot, new_user)]

        if season_rewards != []:
            for v, r in season_rewards:
                r.changer(new_user)

            new_user.last_season_value = v

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

        if user.to_mongo() != new_user.to_mongo():
            embeds = []

            # Sending a message if the daily challenge has been completed
            if new_daily_completion:

                desc = (
                    None if daily_reward is None else f"**Reward:** {daily_reward.desc}"
                )

                embed = ctx.embed(
                    title=":tada: Daily Challenge Complete",
                    description=desc,
                    add_footer=False,
                )
                embeds.append(embed)

            if season_rewards != []:
                _, rewards = zip(*season_rewards)

                r_overview = "\n".join(group_rewards(rewards))

                plural = "s" if len(season_rewards) > 1 else ""

                embed = ctx.embed(
                    title=f":trophy: Unlocked Season Reward{plural}",
                    description=r_overview,
                    add_footer=False,
                )
                embeds.append(embed)

            if embeds != []:
                await ctx.respond(embeds=embeds, ephemeral=True)

            # Sending a message with the achievements that have been completed
            if user.achievements != new_user.achievements:
                files, extra = self.get_files_from_earned(a_earned)

                # Getting a list of rewards out of all the achievements
                rewards = [
                    b
                    for a in a_earned.values()
                    for c in a
                    if (b := c[0].reward) is not None
                ]

                content = ""

                if len(rewards) > 1:
                    r_overview = "\n> ".join(group_rewards(rewards))

                    content += f"**Rewards Overview:**\n> {r_overview}\n** **\n"

                if extra:
                    content += f"and {extra} more achievements..."

                await ctx.respond(content=content, files=files, ephemeral=True)

            # Replacing the user data with the new state
            await self.bot.mongo.replace_user_data(new_user, ctx.author)


def setup(bot):
    bot.add_cog(Events(bot))
