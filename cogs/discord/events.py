import copy
from datetime import datetime

import discord
import humanize
from discord.ext import commands
from discord.ext.commands import errors
from PIL import ImageDraw
from rapidfuzz import fuzz, process

import icons
from challenges.achievements import check_achievements, check_categories
from challenges.daily import get_daily_challenges
from challenges.rewards import group_rewards
from challenges.season import check_season_rewards
from constants import ACHIEVEMENTS_SHOWN, SUPPORT_SERVER_INVITE
from helpers.errors import ImproperArgument, OnGoingTest
from helpers.image import save_discord_static_img
from helpers.ui import create_link_view, get_log_embed
from helpers.user import get_user_cmds_run
from helpers.utils import filter_commands, format_command, get_command_name
from static.assets import achievement_base, uni_sans_heavy

SEASON_PLACING_TIERS = (
    (1, 1),
    (2, 2),
    (3, 3),
    (4, 5),
    (6, 10),
    (11, 25),
    (26, 50),
    (51, 100),
)


def _generate_achievement_image(name, icon):
    img = achievement_base.copy()

    if icon is not None:
        img_icon = icon.copy().resize((95, 95))
        img.paste(img_icon, (52, 52), img_icon)

    draw = ImageDraw.Draw(img)
    draw.text((240, 110), name, font=uni_sans_heavy)

    return save_discord_static_img(img, "achievement")


class Events(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _get_season_tier_index(self, user) -> tuple[int, int]:
        # The season leaderboard
        lb = self.bot.lbs[1].stats[0]

        # Getting the user's placing
        placing = lb.get_placing(user.id)

        return (
            next(
                (
                    i
                    for i, (t1, t2) in enumerate(SEASON_PLACING_TIERS)
                    if placing in range(t1, t2 + 1)
                ),
                None,
            ),
            placing,
        )

    async def log_interaction(self, ctx):
        # Logging the interaction

        command = format_command(ctx.command)

        embed = get_log_embed(
            ctx, title=None, additional=f"**Command:** {ctx.prefix}{command}"
        )

        await self.bot.cmd_wh.send(embed=embed)

    async def get_guild_log_format(self, guild):
        if guild.name is None:
            guild = await self.bot.fetch_guild(guild.id)

        return f"**Guild Name:** {guild.name}\n**Guild ID:** {guild.id}"

    @commands.Cog.listener()
    async def on_guild_join(self, guild):
        embed = self.bot.default_embed(
            title="Added to Guild",
            description=await self.get_guild_log_format(guild),
        )
        await self.bot.guild_wh.send(embed=embed)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild):
        embed = self.bot.error_embed(
            title="Removed from Guild",
            description=await self.get_guild_log_format(guild),
        )
        await self.bot.guild_wh.send(embed=embed)

    @staticmethod
    async def send_basic_error(
        ctx, *, title, desc=None, severe=False, ephemeral=False, view=None
    ):
        try:
            added = f"{icons.danger} `ERROR!`" if severe else icons.caution

            embed = ctx.error_embed(title=f"{added} {title}", description=desc)

            if view is None:
                await ctx.respond(embed=embed, ephemeral=ephemeral)

            else:
                await ctx.respond(embed=embed, ephemeral=ephemeral, view=view)

        except discord.errors.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        await self.handle_error(ctx, error)

    @commands.Cog.listener()
    async def on_application_command_error(self, ctx, error):
        await self.handle_error(ctx, error)

    async def handle_error(self, ctx, error):
        if isinstance(error, (discord.errors.CheckFailure, commands.CheckFailure)):
            if isinstance(error, errors.BotMissingPermissions):
                return await self.handle_check_failure(ctx, error)

            return self.bot.active_end(ctx.author.id)

        if isinstance(error, OnGoingTest):
            return await self.bot.handle_ongoing_test_error(ctx.respond)

        self.bot.active_end(ctx.author.id)

        if isinstance(error, errors.UserInputError):
            return await self.handle_user_input_error(ctx, error)

        if ctx.is_slash is False:
            if isinstance(error, errors.CommandNotFound):
                return await self.handle_command_not_found(ctx)

        if hasattr(error, "original") and isinstance(
            error.original, discord.errors.Forbidden
        ):
            try:
                await self.send_basic_error(
                    ctx,
                    title="Permission Error",
                    desc="I am missing the correct permissions",
                )
            except Exception:
                pass

            return

        await self.handle_unexpected_error(ctx, error)

    async def handle_command_not_found(self, ctx):
        cmds = filter_commands(ctx, ctx.bot.walk_commands())

        cmd_names = [get_command_name(cmd) for cmd in cmds]

        name, *_ = process.extractOne(
            ctx.message.content, cmd_names, scorer=fuzz.WRatio
        )

        await self.send_basic_error(
            ctx,
            title="Command Not Found",
            desc=(
                f"Type `{ctx.prefix}help` for a full list of commands\n\n"
                f"Did you mean `{ctx.prefix}{name}`?"
            ),
        )

    async def handle_check_failure(self, ctx, error):
        if isinstance(error, errors.BotMissingPermissions):
            await self.send_basic_error(
                ctx, title="Bot Missing Permissions", severe=True
            )

        return self.bot.active_end(ctx.author.id)

    async def handle_user_input_error(self, ctx, error):
        if isinstance(error, errors.BadArgument):
            message = str(error)

            if isinstance(error, ImproperArgument) and error.options:
                options = " ".join(f"`{o}`" for o in error.options)
                message += f"\n\n**Did you mean?**\n{options}"

            return await self.send_basic_error(
                ctx, title="Invalid Argument", desc=message
            )
        elif isinstance(error, errors.MissingRequiredArgument):
            cmd_signature = format_command(ctx.command)

            return await self.send_basic_error(
                ctx,
                title="Invalid Input",
                desc=(
                    f"Missing required argument `{error.param.name}`\n\n"
                    f"Correct Usage: `{ctx.prefix}{cmd_signature}`"
                ),
            )

        await self.send_basic_error(
            ctx,
            title="Invalid Input",
            desc=(
                "Your input is malformed\n"
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

        command = format_command(ctx.command)

        embed = get_log_embed(
            ctx,
            title="Unexpected Error",
            additional=f"**Command:** {ctx.prefix}{command}",
            error=True,
        )

        await self.bot.log_the_error(embed, error)

    @commands.Cog.listener()
    async def on_command(self, ctx):
        await self.log_interaction(ctx)

    @commands.Cog.listener()
    async def on_application_command(self, ctx):
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
        await self.handle_command_completion(ctx)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx):
        await self.handle_command_completion(ctx)

    async def handle_command_completion(self, ctx):
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
        c_completed = {}

        done_checking = False

        while done_checking is False:

            new_a = False

            # Looping through the finished achievements
            async for a, count, cv, identifier in check_achievements(ctx, new_user):
                a_earned[identifier] = a_earned.get(identifier, []) + [(a, count, cv)]
                new_a = True

                # Adding achievemnt to document
                insert_count = 0 if count is None else count
                current = new_user.achievements.get(a.name, [])

                current.insert(insert_count, datetime.utcnow())

                new_user.achievements[a.name] = current

            # Looping through the finished categories
            for n, c in check_categories(new_user, user):
                c_completed[n] = c.reward

                if c.changer is not None:
                    new_user = c.changer(new_user)

            # Continues checking until no new achievements are given in a round (allows chaining achievements)
            if new_a is False:
                done_checking = True

        # Daily challenges

        challenges, daily_reward = get_daily_challenges()

        new_user.daily_completion = [
            n or await c.is_completed(ctx, new_user)
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

        cmd_name = get_command_name(ctx.command)

        cmds = get_user_cmds_run(self.bot, new_user)

        if cmd_name not in cmds:
            new_cache_cmds = self.bot.cmds_run.get(ctx.author.id, set()) | {cmd_name}

            # Updating in database if the user document was going to be updated anyways or there are 3 or more commands not saved in database
            if user.to_mongo() != new_user.to_mongo() or len(new_cache_cmds) >= 3:
                new_user.cmds_run = list(set(new_user.cmds_run) | new_cache_cmds)

            else:
                self.bot.cmds_run[ctx.author.id] = new_cache_cmds

        # Actually sending stuff
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

                content = ""

                if c_completed:

                    r_overview = "\n".join(
                        f"{n} - {r.desc}" if r else n for n, r in c_completed.items()
                    )

                    content += f":trophy: **Categories Completed:**\n{r_overview}"

                if extra:
                    content += f"\n\n{extra} more achievements not shown..."

                content += f"\n\nCheck all your achievements with `{ctx.prefix}achievements`\n** **"

                await ctx.respond(content=content, files=files, ephemeral=True)

            embeds = []

            # Daily streak
            if user.streak != new_user.streak:
                emoji = icons.success if new_user.streak > user.streak else icons.danger

                plural = "s" if new_user.streak > 1 else ""

                embed = ctx.embed(
                    title=f"{emoji} Your daily streak is now `{new_user.streak} day{plural}`",
                    add_footer=False,
                )

                embeds.append(embed)

            # Updating the user if their season placing moved up or down a tier
            start_placing_index, start_placing = self._get_season_tier_index(user)
            after_placing_index, after_placing = self._get_season_tier_index(new_user)

            if after_placing is not None and start_placing_index != after_placing_index:

                after_ordinal_placing = humanize.ordinal(after_placing)

                if start_placing is None:
                    placing_display = ""

                else:
                    icon = (
                        icons.up_arrow
                        if start_placing_index > after_placing_index
                        else icons.down_arrow
                    )

                    placing_diff = abs(after_placing - start_placing)

                    placing_display = f" ({icon}{placing_diff})"

                embed = ctx.embed(
                    title=f"Your season placing is now {after_ordinal_placing}{placing_display}",
                    add_footer=False,
                )
                embed.set_footer(
                    text=f"View the full leaderboard with {ctx.prefix}leaderboard"
                )

                embeds.append(embed)

            if embeds != []:
                await ctx.respond(embeds=embeds, ephemeral=True)

            # Replacing the user data with the new state
            await self.bot.mongo.replace_user_data(new_user, ctx.author)


def setup(bot):
    bot.add_cog(Events(bot))
