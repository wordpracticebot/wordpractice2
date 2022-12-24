import asyncio
import importlib
import inspect
import pkgutil
import time
import traceback
from collections import Counter
from io import BytesIO
from typing import TYPE_CHECKING, Union

import aiohttp
import discord
from discord import InteractionType
from discord.ext import bridge, commands

import cogs
import config
from data.constants import (
    ERROR_CLR,
    GITHUB_LINK,
    INFO_VIDEO,
    LB_DISPLAY_AMT,
    LB_LENGTH,
    PERMISSONS,
    PRIMARY_CLR,
    PRIVACY_POLICY_LINK,
    RULES_LINK,
    SUPPORT_SERVER_INVITE,
    TEST_EXPIRE_TIME,
    TEST_ZONES,
)
from helpers.errors import OnGoingTest
from helpers.ui import BaseView, CustomEmbed, create_link_view, get_log_embed
from helpers.utils import get_hint, message_banned_user

if TYPE_CHECKING:
    from cogs.utils.mongo import User


class LBCategory:
    def __init__(self, parent_index, index, bot, name, unit, get_stat):
        self.parent_index = parent_index
        self.index = index

        self.bot = bot
        self.name = name
        self.unit = unit

        self.get_stat = get_stat

    @property
    def lb_key(self):
        return f"lb.{self.parent_index}.{self.index}"

    async def get_placing(self, user_id):
        placing = await self.bot.redis.zrevrank(self.lb_key, user_id)

        if placing is None or placing > LB_LENGTH:
            return None

        return placing

    async def remove_user(self, user_id):
        return await self.bot.redis.zrem(self.lb_key, user_id)

    def get_initial_value(self, ctx: "Context"):
        return ctx.initial_values[self.parent_index][self.index]

    async def get_lb_data(self, end=LB_DISPLAY_AMT):
        raw_data = await self.bot.redis.zrevrange(self.lb_key, 0, end, withscores=True)

        return {int(u.decode()): v for u, v in raw_data}

    async def get_lb_values_from_score(self, min, max):
        raw_data = await self.bot.redis.zrevrangebyscore(
            self.lb_key, min=min, max=max, withscores=True
        )

        _, values = zip(*raw_data)

        return list(values)

    @classmethod
    def new(cls, *args, **kwargs):
        def do_it(parent_index, index):
            return cls(parent_index, index, *args, **kwargs)

        return do_it


class Leaderboard:
    def __init__(
        self,
        index: int,
        *,
        title: str,
        emoji: str,
        default: int,
        stats: list[LBCategory],
        check=None,
        priority=0,
    ):
        self.index = index

        # Meta data
        self.title = title
        self.emoji = emoji

        self.stats = self.initialize_stats(stats)

        if len(self.stats) <= default:
            raise Exception("Default out of range")

        # Default stat index
        self.default = default

        self._check = check

        self.priority = priority

    def initialize_stats(self, stats):
        return [s(self.index, i) for i, s in enumerate(stats)]

    @property
    def desc(self):
        return ", ".join(s.name for s in self.stats)

    async def check(self, ctx: "Context"):
        if self._check is None:
            return True

        return await self._check(ctx)

    @classmethod
    def new(cls, *args, **kwargs):
        return lambda index: cls(index, *args, **kwargs)


class HSLeaderboard(Leaderboard):
    @property
    def desc(self):
        return super().desc + " Test"


def unqualify(name):
    return name.rsplit(".", maxsplit=1)[-1]


# https://github.com/python-discord/bot/blob/main/bot/utils/extensions.py
def get_exts():
    for module in pkgutil.walk_packages(cogs.__path__, f"{cogs.__name__}."):

        # Not loading modules that start with underscore
        if unqualify(module.name).startswith("_"):
            continue

        imported = importlib.import_module(module.name)
        # Checking for setup function to determine if it is an extension
        if not inspect.isfunction(getattr(imported, "setup", None)):
            continue

        yield module.name


class WelcomeView(BaseView):
    def __init__(self, ctx: "Context", callback, response):
        super().__init__(ctx, timeout=12)

        self.callback = callback
        self.response = response

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.primary)
    async def accept(self, button, interaction):
        user = await self.ctx.bot.mongo.fetch_user(interaction.user, create=True)

        embed = self.ctx.default_embed(
            title="Rules Accepted",
            description="We hope that you enjoy your time using wordPractice",
        )

        embed.add_field(
            name="Confused?",
            value="Watch our informational video below or type `/help` for a list of commands",
            inline=False,
        )

        embed.add_field(
            name="Got ask questions?",
            value="Join our support server below!",
            inline=False,
        )

        embed.set_thumbnail(url="https://i.imgur.com/MF0xiLu.png")

        view = create_link_view(
            {
                "Server": SUPPORT_SERVER_INVITE,
                "Video": INFO_VIDEO,
                "Github": GITHUB_LINK,
            }
        )

        self.ctx.initial_user = user
        self.ctx.add_leaderboard_values()

        if self.response:
            await interaction.response.edit_message(embed=embed, view=view)
        else:
            await self.ctx.edit(embed=embed, view=view)

        await self.ctx.bot.handle_after_welcome_check(self.ctx)

        if self.callback is not None:
            if self.response:
                await self.callback()
            else:
                await self.callback(interaction)

        self.stop()

    async def start(self):
        embed = self.ctx.default_embed(
            title="Welcome to wordPractice!",
            description=(
                "I'm the most feature dense typing test Discord Bot. I allow\n"
                "you to practice your typing skills while having fun!\n\n"
                "**Rules and Privacy Policy**\n"
                "Please take a second to read our privacy policy and rules\n"
                "below."
            ),
        )

        embed.set_thumbnail(url="https://i.imgur.com/2vUD4NF.png")

        # Adding the links
        item = discord.ui.Button(label="Privacy Policy", url=PRIVACY_POLICY_LINK)
        self.add_item(item)

        item = discord.ui.Button(label="Rules", url=RULES_LINK)
        self.add_item(item)

        await self.ctx.respond(embed=embed, view=self, ephemeral=True)


class CustomContextItems:
    def __init__(self, bot: "WordPractice" = None):
        self.bot = bot

        # Initial stats
        self.initial_user: User = None
        self.initial_values = []

        self.achievements_completed = []  # list of additional achievements completed

        self.no_completion = False

        self.other_author = None

        # Hint is chosen when defining context to ensure a consistent hint throughout each response
        self._hint = get_hint()

    @property
    def hint(self):
        return self._hint.format(self.prefix)

    @property
    def theme(self):
        return (
            int(self.initial_user.theme[1].replace("#", "0x"), 16)
            if self.initial_user
            else None
        )

    @property
    def error_embed(self):
        return self.bot.error_embed

    @property
    def default_embed(self):
        return self.bot.default_embed

    @property
    def custom_embed(self):
        return self.bot.custom_embed

    def embed(self, **kwargs):
        color = kwargs.pop("color", self.theme or PRIMARY_CLR)
        return CustomEmbed(self.bot, color=color, hint=self.hint, **kwargs)

    def add_leaderboard_values(self):
        self.initial_values = self.bot.get_leaderboard_values(self.initial_user)

    async def add_initial_stats(self, user):
        # Getting the initial user
        self.initial_user = await self.bot.mongo.fetch_user(user)

        if self.initial_user is None:
            return

        # Getting the initial placing for each category
        self.add_leaderboard_values()


class CustomAppContext(bridge.BridgeApplicationContext, CustomContextItems):
    def __init__(self, *args, **kwargs):

        bridge.BridgeApplicationContext.__init__(self, *args, **kwargs)
        CustomContextItems.__init__(self, self.bot)

        self.prefix = "/"
        self.is_slash = True

    @property
    def user(self):
        return self.other_author or self.interaction.user

    author = user


class CustomPrefixContext(bridge.BridgeExtContext, CustomContextItems):
    def __init__(self, *args, **kwargs):
        bridge.BridgeExtContext.__init__(self, *args, **kwargs)
        CustomContextItems.__init__(self, self.bot)

        self.is_slash = False

    @property
    def author(self):
        return self.other_author or self.message.author

    async def _respond(self, *args, **kwargs):
        kwargs.pop("ephemeral", None)

        kwargs = kwargs | {"mention_author": False}

        return await super()._respond(*args, **kwargs)


Context = Union[CustomPrefixContext, CustomAppContext]


class WordPractice(bridge.AutoShardedBot):
    def __init__(self, **kwargs):

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        super().__init__(**kwargs, loop=self.loop)

        self.add_check(
            commands.bot_has_permissions(
                read_messages=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True,
                external_emojis=True,
            ).predicate
        )

        name = " your wpm \N{EYES} | %help"

        self.activity = discord.Activity(type=discord.ActivityType.watching, name=name)
        self.session = aiohttp.ClientSession(loop=self.loop)

        self.cooldowns = {}

        # Cache
        self.cmds_run = {}  # user_id: set{cmds}
        self.avg_perc = []  # [wpm (33% 66%), raw, acc]

        # Not using MaxConcurrency because it's based on context so it doesn't work with users who join race
        self.active_tests = {}  # user_id: timestamp

        self.spam_control = commands.CooldownMapping.from_cooldown(
            6, 8, commands.BucketType.user  # rate, per
        )
        self.spam_count = Counter()

        # Leaderboards

        def get_hs(s):
            return lambda u: u.highspeed[s].wpm

        async def season_check(ctx: Context):
            season_data = await ctx.bot.mongo.get_season_info()

            return season_data is not None and season_data["enabled"]

        self.lbs = [
            Leaderboard.new(
                title="All Time",
                emoji="\N{EARTH GLOBE AMERICAS}",
                stats=[LBCategory.new(self, "Words Typed", "words", lambda u: u.words)],
                default=0,
                priority=1,
            ),
            Leaderboard.new(
                title="Monthly Season",
                emoji="\N{SPORTS MEDAL}",
                stats=[LBCategory.new(self, "Experience", "xp", lambda u: u.xp)],
                default=0,
                check=season_check,
                priority=2,
            ),
            Leaderboard.new(
                title="24 Hour",
                emoji="\N{CLOCK FACE ONE OCLOCK}",
                stats=[
                    LBCategory.new(self, "Experience", "xp", lambda u: sum(u.xp_24h)),
                    LBCategory.new(
                        self, "Words Typed", "words", lambda u: sum(u.words_24h)
                    ),
                ],
                default=0,
            ),
            Leaderboard.new(
                title="High Score",
                emoji="\N{RUNNER}",
                stats=[
                    LBCategory.new(self, s.capitalize(), "wpm", get_hs(s))
                    for s in TEST_ZONES.keys()
                ],
                default=1,
            ),
        ]

        self.initialize_lbs()

        self.start_time = time.time()

        self.load_exts()

    def initialize_lbs(self):
        for i, lb in enumerate(self.lbs):
            self.lbs[i] = lb(i)

    def get_leaderboard_values(self, user):
        values = []

        for lb in self.lbs:
            category = []

            for stat in lb.stats:
                category.append(stat.get_stat(user))

            values.append(category)

        return values

    def active_start(self, user_id: int):
        timestamp = self.active_tests.get(user_id, None)

        # Checking if the user is in an active test and it isn't expired
        if timestamp is not None and time.time() - timestamp < TEST_EXPIRE_TIME + 1:
            raise OnGoingTest()

        self.active_tests[user_id] = time.time()

    def active_end(self, user_id: int):
        if user_id in self.active_tests:
            del self.active_tests[user_id]

    async def handle_after_welcome_check(self, ctx: Context):
        # Checking if the user is banned
        if ctx.initial_user.banned:
            embed = ctx.error_embed(
                title="You are banned",
                description="Join the support server and create a ticket to request a ban appeal",
            )
            view = create_link_view({"Support Server": SUPPORT_SERVER_INVITE})

            await ctx.respond(embed=embed, view=view, ephemeral=True)

            return True

        return False

    @property
    def mongo(self):
        return self.get_cog("Mongo")

    @property
    def redis(self):
        return self.get_cog("Redis").pool

    @property
    def log(self):
        return self.get_cog("Logging").log

    def error_embed(self, **kwargs):
        color = kwargs.pop("color", ERROR_CLR)
        return CustomEmbed(self, color=color, add_footer=False, **kwargs)

    def default_embed(self, **kwargs):
        color = kwargs.pop("color", PRIMARY_CLR)
        return CustomEmbed(self, color=color, add_footer=False, **kwargs)

    def custom_embed(self, **kwargs):
        return CustomEmbed(self, **kwargs)

    async def on_shard_ready(self, shard_id):
        self.log.info(f"Shard {shard_id} ready")

    async def get_application_context(self, interaction, cls=CustomAppContext):
        ctx = await super().get_application_context(interaction, cls)

        await ctx.add_initial_stats(interaction.user)

        return ctx

    async def get_context(self, message, *, cls=CustomPrefixContext):
        ctx = await super().get_context(message, cls=cls)

        if ctx is None:
            return

        if ctx.command is None:
            return ctx

        await ctx.add_initial_stats(message.author)

        return ctx

    def load_exts(self):
        # Finding files in cogs folder that end with .py
        for ext in get_exts():
            # Loading the extension
            try:
                self.load_extension(ext)
            except Exception:
                self.log.warning(f"Failed to load extension: {ext}")
                traceback.print_exc()

    def create_invite_link(self):
        return discord.utils.oauth_url(
            client_id=self.user.id,
            permissions=discord.Permissions(permissions=PERMISSONS),
            redirect_uri=SUPPORT_SERVER_INVITE,
            scopes=("bot", "applications.commands"),
        )

    async def handle_ongoing_test_error(self, send):
        await send(
            "You are currently in another test, please finish it before starting a new one!",
            ephemeral=True,
        )

    async def log_the_error(self, embed, error):
        msg = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )

        buffer = BytesIO(msg.encode("utf-8"))
        file = discord.File(buffer, filename="text.txt")

        await self.error_wh.send(embed=embed, file=file)

        self.log.warning(msg)

    async def handle_new_user(self, ctx: Context, callback=None, response=True):
        view = WelcomeView(ctx, callback, response)
        await view.start()

    async def on_interaction(self, interaction):
        if interaction.type is InteractionType.application_command:

            ctx = await self.get_application_context(interaction)

            # Asking the user to accept the rules before using the bot
            if ctx.initial_user is None:

                async def callback():
                    await self.process_application_commands(interaction)

                return await self.handle_new_user(ctx, callback=callback)

            if await self.handle_after_welcome_check(ctx):
                return

        # Processing command
        await self.process_application_commands(interaction)

    async def process_commands(self, message):
        if message.author.bot:
            return

        ctx = await self.get_context(message)

        if ctx is None:
            return

        if ctx.command is not None:
            # Asking the user to accept the rules before using the bot
            if ctx.initial_user is None:

                async def callback():
                    await self.invoke(ctx)

                return await self.handle_new_user(ctx, callback=callback)

            if await self.handle_after_welcome_check(ctx):
                return

            # Spam control
            # https://github.com/Rapptz/RoboDanny/blob/rewrite/bot.py
            bucket = self.spam_control.get_bucket(message)

            current = message.created_at.replace().timestamp()
            retry_after = bucket.update_rate_limit(current)

            author_id = message.author.id

            if retry_after and author_id != self.owner_id:
                self.spam_count[author_id] += 1

                if (amt := self.spam_count[author_id]) >= 3:
                    del self.spam_count[author_id]

                    reason = "Spamming commands"

                    # Banning the user
                    user_data = await ctx.bot.mongo.add_inf(
                        ctx, ctx.author, ctx.initial_user, reason
                    )

                    # Updating the user's data
                    await self.mongo.replace_user_data(user_data)

                    await message_banned_user(ctx, ctx.author, reason)

                else:
                    # Flagging the user for spamming commands
                    embed = get_log_embed(
                        ctx,
                        title="User Spamming Commands",
                        additional=f"**Times Flagged:** {amt}",
                        error=True,
                    )

                    await self.impt_wh.send(embed=embed)

            else:
                self.spam_count.pop(author_id, None)

        await self.invoke(ctx)

    @discord.utils.cached_property
    def cmd_wh(self):
        return discord.Webhook.from_url(config.COMMAND_LOG, session=self.session)

    @discord.utils.cached_property
    def test_wh(self):
        return discord.Webhook.from_url(config.TEST_LOG, session=self.session)

    @discord.utils.cached_property
    def impt_wh(self):
        return discord.Webhook.from_url(config.IMPORTANT_LOG, session=self.session)

    @discord.utils.cached_property
    def error_wh(self):
        return discord.Webhook.from_url(config.ERROR_LOG, session=self.session)

    @discord.utils.cached_property
    def guild_wh(self):
        return discord.Webhook.from_url(config.GUILD_LOG, session=self.session)

    async def on_ready(self):
        self.log.info("The bot is ready!")

    async def close(self):
        await super().close()

        await self.session.close()
        await self.redis.close()

    def run(self):
        super().run(config.BOT_TOKEN, reconnect=True)
