import asyncio
import importlib
import inspect
import pkgutil
import sys
import time
import traceback
from collections import Counter

import aiohttp
import discord
from discord import InteractionType
from discord.ext import commands

import cogs
from constants import ERROR_CLR, PERMISSONS, PRIMARY_CLR, SUPPORT_SERVER
from helpers.ui import BaseView, CustomEmbed

# TODO: use max concurrency for typing test
# TODO: check if user is banned when giving roles
# TODO: build typing test gifs more efficiently
# TODO: customize pacer type (horizonal, vertical)


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


class WordPractice(commands.AutoShardedBot):
    def __init__(self, config, **kwargs):

        self.config = config

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
            type=discord.ActivityType.watching, name=" your wpm 👀 "
        )
        self.session = aiohttp.ClientSession(loop=self.loop)

        # Spam protection
        self.spam_control = commands.CooldownMapping.from_cooldown(
            8, 10.0, commands.BucketType.user
        )
        self.spam_counter = Counter()

        # Cache
        self.user_cache = {}
        self.lbs = []

        self.start_time = time.time()
        self.last_lb_update = time.time()

        self.load_exts()

    def embed(self, **kwargs):
        color = kwargs.pop("color", PRIMARY_CLR)
        return CustomEmbed(self, color=color, **kwargs)

    def error_embed(self, **kwargs):
        color = kwargs.pop("color", ERROR_CLR)
        return CustomEmbed(self, color=color, **kwargs)

    @property
    def mongo(self):
        return self.get_cog("Mongo")

    @property
    def log(self):
        return self.get_cog("Logging").log

    async def on_shard_ready(self, shard_id):
        self.log.info(f"Shard {shard_id} ready")

    def load_exts(self):
        # Finding files in cogs folder that end with .py
        for ext in get_exts():
            # Loading the extension
            try:
                self.load_extension(ext)
            except:
                print(f"Failed to load extension: {ext}", file=sys.stderr)
                traceback.print_exc()

    def create_invite_link(self):
        return discord.utils.oauth_url(
            client_id=self.user.id,
            permissions=discord.Permissions(permissions=PERMISSONS),
            scopes=("bot", "applications.commands"),
        )

    async def on_interaction(self, interaction):
        if interaction.type is InteractionType.application_command:
            # TODO: add ratelimiting when pycord adds cooldowns for slash commands

            user = await self.mongo.fetch_user(interaction.user, create=True)

            if user is None:
                return

            # Checking if the user is banned
            if user.banned:
                embed = self.error_embed(
                    title="You are banned",
                    description="Join the support server and create a ticket for a ban appeal",
                    add_footer=False,
                )
                view = BaseView(personal=True)

                item = discord.ui.Button(
                    style=discord.ButtonStyle.link,
                    label="Click here!",
                    url=SUPPORT_SERVER,
                )
                view.add_item(item=item)

                ctx = await self.get_application_context(interaction)

                return await ctx.respond(embed=embed, view=view, ephemeral=True)

        # Processing command
        await self.process_application_commands(interaction)

    @discord.utils.cached_property
    def cmd_wh(self):
        hook = discord.Webhook.from_url(self.config.COMMAND_LOG, session=self.session)
        return hook

    @discord.utils.cached_property
    def test_wh(self):
        hook = discord.Webhook.from_url(self.config.TEST_LOG, session=self.session)
        return hook

    @discord.utils.cached_property
    def impt_wh(self):
        hook = discord.Webhook.from_url(self.config.IMPORTANT_LOG, session=self.session)
        return hook

    async def close(self):
        await super().close()
        await self.session.close()

    def run(self):
        super().run(self.config.BOT_TOKEN, reconnect=True)
