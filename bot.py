import asyncio
import importlib
import inspect
import pkgutil
import time
import traceback
from io import BytesIO

import aiohttp
import discord
from discord import InteractionType
from discord.ext import bridge, commands

import cogs
import config
from constants import (
    ERROR_CLR,
    GITHUB_LINK,
    INFO_VIDEO,
    LB_LENGTH,
    PERMISSONS,
    PRIMARY_CLR,
    PRIVACY_POLICY_LINK,
    RULES_LINK,
    SUPPORT_SERVER_INVITE,
    TEST_ZONES,
)
from helpers.errors import OnGoingTest
from helpers.ui import BaseView, CustomEmbed, create_link_view
from helpers.utils import get_hint

THIN_SPACE = "\N{THIN SPACE}"


class LBCategory:
    def __init__(self, bot, name, unit, query, get_stat):
        self.bot = bot
        self.name = name
        self.unit = unit

        self.data = None

        self.query = query
        self.get_stat = get_stat

    async def update(self):
        cursor = self.bot.mongo.db.users.aggregate(
            [
                {
                    "$project": {
                        "_id": 1,
                        "name": 1,
                        "discriminator": 1,
                        "status": 1,
                        "count": self.query,
                    }
                },
                {"$sort": {"count": -1}},
                {"$limit": LB_LENGTH},
            ]
        )
        self.data = [i async for i in cursor]

    def get_placing(self, user_id: int):
        if self.data is None:
            return

        return next(
            ((i + 1, u) for i, u in enumerate(self.data) if u["_id"] == int(user_id)),
            None,
        )


class Leaderboard:
    def __init__(
        self,
        title: str,
        desc: str,
        emoji: str,
        default: int,
        stats: list[LBCategory],
    ):
        # Meta data
        self.title = title
        self.desc = desc
        self.emoji = emoji

        self.stats = stats

        if len(self.stats) <= default:
            raise Exception("Default out of range")

        # Default stat index
        self.default = default

    async def update_all(self):
        for stat in self.stats:
            await stat.update()


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
    def __init__(self, ctx):
        super().__init__(ctx, timeout=120)

    async def on_timeout(self):
        pass

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
                "Community Server": SUPPORT_SERVER_INVITE,
                "Video": INFO_VIDEO,
                "Github": GITHUB_LINK,
            }
        )

        self.ctx.initial_user = user

        await interaction.response.edit_message(embed=embed, view=view)

        await self.ctx.bot.handle_after_welcome_check(self.ctx)

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

        accept_time = 5

        embed.set_footer(
            text=f"You will be able to click accept in {accept_time} seconds"
        )

        embed.set_thumbnail(url="https://i.imgur.com/2vUD4NF.png")
        self.accept.disabled = True

        # Adding the links

        item = discord.ui.Button(label="Privacy Policy", url=PRIVACY_POLICY_LINK)
        self.add_item(item)

        item = discord.ui.Button(label="Rules", url=RULES_LINK)
        self.add_item(item)

        await self.ctx.respond(embed=embed, view=self, ephemeral=True)

        # Enabling rules to be accepted after 5 seconds
        await asyncio.sleep(accept_time)

        self.accept.disabled = False

        await self.ctx.edit(view=self)


def get_embed_theme(user):
    return int(user.theme[1].replace("#", "0x"), 16) if user else None


class CustomContextItems:
    def __init__(self):
        self.initial_user = None

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
        return get_embed_theme(self.initial_user)

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

    async def add_initial_user(self, user):
        user_data = await self.bot.mongo.fetch_user(user)

        self.initial_user = user_data


class CustomAppContext(bridge.BridgeApplicationContext, CustomContextItems):
    def __init__(self, *args, **kwargs):

        bridge.BridgeApplicationContext.__init__(self, *args, **kwargs)
        CustomContextItems.__init__(self)

        self.prefix = "/"
        self.is_slash = True

    @property
    def user(self):
        return self.other_author or self.interaction.user

    author = user


class CustomPrefixContext(bridge.BridgeExtContext, CustomContextItems):
    def __init__(self, *args, **kwargs):
        bridge.BridgeExtContext.__init__(self, *args, **kwargs)
        CustomContextItems.__init__(self)

        self.is_slash = False

    @property
    def author(self):
        return self.other_author or self.message.author

    async def _respond(self, *args, **kwargs):
        kwargs.pop("ephemeral", None)

        kwargs = kwargs | {"mention_author": False}

        return await super()._respond(*args, **kwargs)


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

        self.activity = discord.Activity(
            type=discord.ActivityType.watching, name=f" your wpm \N{EYES}{THIN_SPACE}"
        )
        self.session = aiohttp.ClientSession(loop=self.loop)

        self.cooldowns = {}

        # Cache
        self.cmds_run = {}  # user_id: set{cmds}
        self.avg_perc = []  # [wpm (33% 66%), raw, acc]

        # Not using MaxConcurrency because it's based on context so it doesn't work with users who join race
        self.active_tests = []

        # Leaderboards

        def get_hs(s):
            return lambda u: u.highspeed[s].wpm

        # fmt: off
        self.lbs = [
            Leaderboard(
                title="All Time",
                desc="Words Typed",
                emoji="\N{EARTH GLOBE AMERICAS}",
                stats=[LBCategory(self, "Words Typed", "words", "$words", lambda u: u.words)],
                default=0,
            ),
            Leaderboard(
                title="Monthly Season",
                desc="Experience",
                emoji="\N{SPORTS MEDAL}",
                stats=[LBCategory(self, "Experience", "xp", "$xp", lambda u: u.xp)],
                default=0,
            ),
            Leaderboard(
                title="24 Hour",
                desc="Experience, Words Typed",
                emoji="\N{CLOCK FACE ONE OCLOCK}",
                stats=[
                    LBCategory(self,"Experience","xp", {"$sum": {"$arrayElemAt": ["$last24", 1]}}, lambda u: sum(u.last24[1])),
                    LBCategory(self, "Words Typed", "words", {"$sum": {"$arrayElemAt": ["$last24", 0]}}, lambda u: sum(u.last24[0])),
                ],
                default=0,
            ),
            Leaderboard(
                title="High Score",
                desc=f"{', '.join(t.capitalize() for t in TEST_ZONES.keys())} Test",
                emoji="\N{RUNNER}",
                stats=[
                    LBCategory(self, s.capitalize(), "wpm", f"$highspeed.{s}.wpm", get_hs(s)) for s in TEST_ZONES.keys()
                ],
                default=1,
            ),
        ]
        # fmt: on
        self.last_lb_update = time.time()

        self.start_time = time.time()

        self.load_exts()

    def active_start(self, user_id: int):
        # If the user is currently in a test
        if user_id in self.active_tests:
            raise OnGoingTest()

        self.active_tests.append(user_id)

    def active_end(self, user_id: int):
        if user_id in self.active_tests:
            self.active_tests.remove(user_id)

    async def handle_after_welcome_check(self, ctx):
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

        await ctx.add_initial_user(interaction.user)

        return ctx

    async def get_context(self, message, *, cls=CustomPrefixContext):
        ctx = await super().get_context(message, cls=cls)

        await ctx.add_initial_user(message.author)

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

    async def handle_new_user(self, ctx):
        view = WelcomeView(ctx)
        await view.start()

    async def on_interaction(self, interaction):
        if interaction.type is InteractionType.application_command:

            ctx = await self.get_application_context(interaction)

            # Asking the user to accept the rules before using the bot
            if ctx.initial_user is None:
                return await self.handle_new_user(ctx)

            if await self.handle_after_welcome_check(ctx):
                return

        # Processing command
        await self.process_application_commands(interaction)

    async def process_commands(self, message):
        if message.author.bot:
            return

        ctx = await self.get_context(message)

        if ctx.command is not None:

            # Asking the user to accept the rules before using the bot
            if ctx.initial_user is None:
                return await self.handle_new_user(ctx)

            if await self.handle_after_welcome_check(ctx):
                return

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

    async def on_ready(self):
        self.log.info("The bot is ready!")

    async def close(self):
        await super().close()
        await self.session.close()

    def run(self):
        super().run(config.BOT_TOKEN, reconnect=True)
