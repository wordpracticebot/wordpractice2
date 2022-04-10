import asyncio
import importlib
import inspect
import pkgutil
import random
import sys
import time
import traceback
from io import BytesIO

import aiohttp
import discord
from discord import InteractionType
from discord.ext import commands

import cogs
import config
from constants import (
    ERROR_CLR,
    LB_LENGTH,
    PERMISSONS,
    PRIMARY_CLR,
    PRIVACY_POLICY_LINK,
    RULES_LINK,
    SUPPORT_SERVER_INVITE,
    TEST_ZONES,
)
from helpers.ui import BaseView, CustomEmbed
from static.hints import hints


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
            return None

        return next(
            (i + 1 for i, u in enumerate(self.data) if u["_id"] == int(user_id)), None
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


async def _handle_after_welcome_check(bot, interaction, user):
    # Checking if the user is banned
    if user.banned:
        ctx = await bot.get_application_context(interaction)

        embed = ctx.error_embed(
            title="You are banned",
            description="Join the support server and create a ticket for a ban appeal",
        )
        view = BaseView(ctx)

        item = discord.ui.Button(
            style=discord.ButtonStyle.link,
            label="Support Server",
            url=SUPPORT_SERVER_INVITE,
        )
        view.add_item(item=item)

        await ctx.respond(embed=embed, view=view, ephemeral=True)
        return True

    return False


class WelcomeView(BaseView):
    @discord.ui.button(label="Accept", style=discord.ButtonStyle.primary)
    async def accept(self, button, interaction):
        user = await self.ctx.bot.mongo.fetch_user(interaction.user, create=True)

        # TODO: add some kind of basic bot tutorial here
        embed = self.ctx.default_embed(title="Rules Accepted", description="")

        await interaction.message.edit(embed=embed, view=None)

        await _handle_after_welcome_check(self.ctx.bot, interaction, user)

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

        item = discord.ui.Button(label="Privacy Policy", url=PRIVACY_POLICY_LINK)
        self.add_item(item)

        item = discord.ui.Button(label="Rules", url=RULES_LINK)
        self.add_item(item)

        self.embed = embed

        await self.ctx.respond(embed=embed, view=self)


class CustomContext(discord.commands.ApplicationContext):
    def __init__(self, bot, interaction, theme):
        super().__init__(bot, interaction)

        self.theme = theme
        self.testing = False  # if set to true, cooldowns are avoided

        self.no_completion = False

        # Hint is chosen when defining context to ensure a consistent hint throughout each response
        self.hint = random.choice(hints)

    def embed(self, **kwargs):
        color = kwargs.pop("color", self.theme or PRIMARY_CLR)
        return CustomEmbed(self.bot, color=color, hint=self.hint, **kwargs)

    @property
    def error_embed(self):
        return self.bot.error_embed

    @property
    def default_embed(self):
        return self.bot.default_embed

    @property
    def custom_embed(self):
        return self.bot.custom_embed


class WordPractice(commands.AutoShardedBot):
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
            type=discord.ActivityType.watching, name=" your wpm \N{EYES}\N{THIN SPACE}"
        )
        self.session = aiohttp.ClientSession(loop=self.loop)

        self.cooldowns = {}

        # TODO: clear cache every so often

        # Cache
        self.user_cache = {}
        self.cmds_run = {}  # user_id: set{cmds}
        self.avg_perc = []  # [wpm (33% 66%), raw, acc]

        # Leaderboards

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
                desc="Short, Medium and Long Test",
                emoji="\N{RUNNER}",
                stats=[
                    LBCategory(self, s.capitalize(), "wpm", f"$highspeed.{s}.wpm", lambda u: u.highspeed[s].wpm) for s in TEST_ZONES.keys()
                ],
                default=0,
            ),
        ]
        # fmt: on
        self.last_lb_update = time.time()

        self.start_time = time.time()

        self.load_exts()

    @property
    def mongo(self):
        return self.get_cog("Mongo")

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

    async def get_application_context(self, interaction, cls=None):
        user = await self.mongo.fetch_user(interaction.user)

        theme = int(user.theme[1].replace("#", "0x"), 16) if user else None

        if cls is None:
            cls = CustomContext
        return cls(self, interaction, theme)

    def load_exts(self):
        # Finding files in cogs folder that end with .py
        for ext in get_exts():
            # Loading the extension
            try:
                self.load_extension(ext)
            except Exception:
                print(f"Failed to load extension: {ext}", file=sys.stderr)
                traceback.print_exc()

    def create_invite_link(self):
        return discord.utils.oauth_url(
            client_id=self.user.id,
            permissions=discord.Permissions(permissions=PERMISSONS),
            redirect_uri=SUPPORT_SERVER_INVITE,
            scopes=("bot", "applications.commands"),
        )

    async def log_the_error(self, embed, error):
        msg = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )

        buffer = BytesIO(msg.encode("utf-8"))
        file = discord.File(buffer, filename="text.txt")

        await self.error_wh.send(embed=embed, file=file)

        print(msg)

    async def handle_new_user(self, ctx):
        view = WelcomeView(ctx)
        await view.start()

    async def on_interaction(self, interaction):
        if interaction.type is InteractionType.application_command:
            temp_ctx = await self.get_application_context(interaction)

            user = await self.mongo.fetch_user(interaction.user)

            # Asking the user to accept the rules before using the bot
            if user is None:
                return await self.handle_new_user(temp_ctx)

            if await _handle_after_welcome_check(self, interaction, user):
                return

        # Processing command
        await self.process_application_commands(interaction)

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
        print("Ready!")

    async def close(self):
        await super().close()
        await self.session.close()

    def run(self):
        super().run(config.BOT_TOKEN, reconnect=True)
