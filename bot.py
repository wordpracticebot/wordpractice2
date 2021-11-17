import asyncio
import importlib
import inspect
import pkgutil
import sys
import traceback
from collections import Counter

import aiohttp
import discord
from discord.ext import commands

import cogs
import constants
from helpers.ui import CustomEmbed

# TODO: use max concurrency for typing test


def get_exts():
    for module in pkgutil.walk_packages(cogs.__path__, f"{cogs.__name__}."):
        imported = importlib.import_module(module.name)

        # If the module doesn't have a setup function, it's not an extension
        if not inspect.isfunction(getattr(imported, "setup", None)):
            continue

        yield module.name


class CustomContext(commands.Context):
    @discord.utils.copy_doc(discord.Message.reply)
    async def reply(self, content=None, **kwargs):
        # Setting mention author to False by default
        mention = kwargs.pop("mention_author", None)
        if mention is None:
            mention = False

        return await self.message.reply(content, mention_author=mention, **kwargs)


class WordPractice(commands.AutoShardedBot):
    def __init__(self, config, **kwargs):

        self.config = config

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        super().__init__(**kwargs, loop=loop, command_prefix=self.get_prefix)

        self.add_check(
            commands.bot_has_permissions(
                read_messages=True,
                send_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True,
                add_reactions=True,
                external_emojis=True,
            ).predicate
        )

        self.activity = discord.Activity(
            type=discord.ActivityType.watching, name=" for %help"
        )
        self.http_session = aiohttp.ClientSession()

        # TODO: add spam control
        # Spam protection
        self.spam_control = commands.CooldownMapping.from_cooldown(
            10, 12.0, commands.BucketType.user
        )
        self.spam_counter = Counter()

        # Cache
        self.prefix_cache = {}
        self.user_cache = {}

        self.load_exts()

    def embed(self, **kwargs):
        color = kwargs.pop("color", constants.PRIMARY_CLR)
        return CustomEmbed(self, color=color, **kwargs)

    def error_embed(self, **kwargs):
        color = kwargs.pop("color", constants.ERROR_CLR)
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

    # TODO: add server blacklist
    async def on_guild_join(self, guild):
        pass
        # if guild.id in self.blacklist:
        #     await guild.leave()

    async def close(self):
        await super().close()
        await self.http_session.close()

    async def get_context(self, message, *, cls=CustomContext):
        # Using custom context class
        return await super().get_context(message, cls=cls)

    async def on_message(self, message):
        if message.guild is None or message.author.bot:
            return

        await self.process_commands(message)

    # TODO: use epoch discord timestamps for logs

    async def process_commands(self, message):
        ctx = await self.get_context(message)

        # If bot is mentioned it will return prefix
        if message.content == self.user.mention:
            prefix = await self.get_prefix(message)
            embed = self.embed(title=f"My prefix is `{prefix}`\nType `{prefix}help`")
            return await message.reply(embed=embed)

        # Checking if command is valid
        if ctx.command is not None:
            # Processing command to raise command not found in error handler
            return await self.invoke(ctx)

        # Spam protection
        # https://github.com/Rapptz/RoboDanny/blob/rewrite/bot.py
        bucket = self.spam_control.get_bucket(message)
        current = message.created_at.timestamp()

        retry_after = bucket.update_rate_limit(current)
        author_id = message.author.id

        if retry_after and author_id != self.owner_id:
            self.spam_counter[author_id] += 1
            if self.spam_counter[author_id] >= 3:
                # TODO: ban the user
                del self.spam_counter[author_id]
            else:
                pass
                # TODO: log the spamming
            return
        else:
            self.spam_counter.pop(author_id, None)

        # TODO: log command

    async def get_prefix(self, msg):
        if msg.guild.id in self.prefix_cache:
            prefix = self.prefix_cache[msg.guild.id]
        else:
            guild = await self.mongo.fetch_guild(msg.guild)

            prefix = guild.prefix or constants.DEFAULT_PREFIX

            self.prefix_cache[msg.guild.id] = prefix

        return commands.when_mentioned_or(prefix)(self, msg)

    def run(self):
        super().run(self.config.BOT_TOKEN, reconnect=True)
