import json
import random
from itertools import cycle, islice

import discord
from discord.commands import SlashCommandGroup
from discord.ext import commands, tasks
from humanfriendly import format_timespan

import icons
import word_list
from constants import MAX_RACE_JOIN, RACE_EXPIRE_TIME, TEST_RANGE
from helpers.converters import quote_amt, word_amt
from helpers.ui import BaseView


def load_test_file(name):
    with open(f"./word_list/{name}", "r") as f:
        return json.load(f)


class RaceMember:
    def __init__(self, user):
        """
        user: user object
        """
        self.user = user

        # User's database document
        self.data = None

        # The test score (mongo.Score)
        self.result = None


class RaceJoinButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Join", style=discord.ButtonStyle.success)

    async def callback(self, interaction):
        await self.view.add_racer(interaction)


class RaceLeaveButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Leave", style=discord.ButtonStyle.danger)

    async def callback(self, interaction):
        await self.view.remove_racer(interaction)


class RaceJoinView(BaseView):
    def __init__(self, ctx, *test_data):
        super().__init__(ctx, timeout=None, personal=False)

        self.test_data = test_data
        self.racers = {}  # id: user object (for preserve uniqueness)

        # Cooldown for joining the race (prevents spamming join and leave)
        self.race_join_cooldown = commands.CooldownMapping.from_cooldown(
            1, 10, commands.BucketType.member
        )

    async def remove_racer(self, interaction):
        user = interaction.user

        # If the author leaves, the race is ended
        is_author = user.id == self.ctx.author.id

        msg = (
            self.ctx.interaction.message
            or await self.ctx.interaction.original_message()
        )

        if is_author:
            embed = self.ctx.error_embed(
                title=f"{icons.caution} Race Ended",
                description="The race leader left the race",
            )

            await msg.edit(embed=embed, view=None)
            return self.stop()

        if user.id not in self.racers:
            return await interaction.response.send_message(
                "You are not in the race!", ephemeral=True
            )

        del self.racers[user.id]

        embed = self.get_race_join_embed()

        await msg.edit(embed=embed, view=self)

        return await interaction.response.send_message(
            "You left the race", ephemeral=True
        )

    async def add_racer(self, interaction):
        if len(self.racers) == MAX_RACE_JOIN:
            return

        user = interaction.user

        if user.id in self.racers:
            return await interaction.response.send_message(
                "You are already in this race!", ephemeral=True
            )

        msg = (
            self.ctx.interaction.message
            or await self.ctx.interaction.original_message()
        )

        # If the author joins, the race starts
        is_author = user.id == self.ctx.author.id

        if is_author and len(self.racers) == 0:
            return await interaction.response.send_message(
                "You cannot start this race until another user joins!", ephemeral=True
            )

        if is_author:
            if self.children:
                for child in self.children:
                    child.disabled = True

        else:
            bucket = self.race_join_cooldown.get_bucket(interaction.message)

            retry_after = bucket.update_rate_limit()

            if retry_after:
                timespan = format_timespan(retry_after)

                return await interaction.response.send_message(
                    f"Sorry you are being rate limited, try again in {timespan}",
                    ephemeral=True,
                )

        self.racers[user.id] = RaceMember(user)
        embed = self.get_race_join_embed(is_author)

        await msg.edit(embed=embed, view=self)

        if is_author:
            self.stop()
            await Typing.do_race(self.ctx, self.racers, *self.test_data)

        else:
            return await interaction.response.send_message(
                "You joined the race", ephemeral=True
            )

    @property
    def total_racers(self):
        return len(self.racers)

    # Using a task to expire the race because the built in view timeout restarts after each interaction
    @tasks.loop(seconds=RACE_EXPIRE_TIME, count=2)
    async def timeout_race(self):
        if self.timeout_race.current_loop == 1:
            await self.send_expire_race_message()
            self.stop()

    async def send_expire_race_message(self):
        timespan = format_timespan(RACE_EXPIRE_TIME)

        embed = self.ctx.error_embed(
            title=f"{icons.caution} Race Expired",
            description=f"The race was not started in {timespan}",
        )

        await self.ctx.interaction.edit_original_message(embed=embed, view=None)

    def get_race_join_embed(self, started=False):
        embed = self.ctx.embed(
            title="Typing Test Race",
            description=f"**{self.total_racers} / {MAX_RACE_JOIN}** Racers\n\n",
        )

        if started:
            embed.description += "You can no longer join the race"
        else:
            embed.description += "The race leader can start the race my joining it"

        return embed

    async def start(self):
        embed = self.get_race_join_embed()

        race_join_button = RaceJoinButton()
        race_leave_button = RaceLeaveButton()

        self.add_item(race_join_button)
        self.add_item(race_leave_button)

        await self.ctx.respond(embed=embed, view=self)

        self.timeout_race.start()


class Typing(commands.Cog):
    """Typing test related commands"""

    emoji = "\N{KEYBOARD}"
    order = 2

    def __init__(self, bot):
        self.bot = bot

    tt_group = SlashCommandGroup("tt", "Take a typing test")
    race_group = SlashCommandGroup(
        "race",
        f"Take a multiplayer typing test. Up to {MAX_RACE_JOIN} other users can join your race.",
    )

    @tt_group.command()
    async def dictionary(self, ctx, length: word_amt()):
        """Take a dictionary typing test"""
        quote = await self.handle_dictionary_input(ctx, length)

        await self.do_typing_test(ctx, True, quote)

    @tt_group.command()
    async def quote(self, ctx, length: quote_amt()):
        """Take a quote typing test"""
        quote = await self.handle_quote_input(ctx, length)

        await self.do_typing_test(ctx, False, quote)

    @race_group.command()
    async def dictionary(self, ctx, length: word_amt()):
        """Take a multiplayer dictionary typing test"""
        quote = await self.handle_dictionary_input(ctx, length)

        await self.show_race_start(ctx, True, quote)

    @race_group.command()
    async def quote(self, ctx, length: quote_amt()):
        """Take a multiplayer quote typing test"""
        quote = await self.handle_quote_input(ctx, length)

        await self.show_race_start(ctx, False, quote)

    @commands.user_command(name="Typing Challenge")
    async def race_challenge(self, ctx, member: discord.Member):
        # TODO: send a dropdown to choose race
        pass

    async def handle_dictionary_input(self, ctx, length: int):
        if length not in range(*TEST_RANGE):
            raise commands.BadArgument(
                f"The typing test must be between {TEST_RANGE[0]} and {TEST_RANGE[1]} words"
            )

        user = await self.bot.mongo.fetch_user(ctx.author)

        words = load_test_file(word_list.languages[user.language]["levels"][user.level])

        return random.sample(words, length)

    async def handle_quote_input(self, ctx, length: str):
        test_range = word_list.quotes["lengths"][length]

        quotes = load_test_file("quotes.json")

        start = random.randint(0, len(quotes) - 1)

        # Selecting consecutive items from list of sentences
        return list(islice(cycle(quotes), start, start + random.randint(*test_range)))

    async def show_race_start(self, ctx, is_dict, quote):
        # Storing is_dict and quote in RaceJoinView because do_race method will be called inside it
        view = RaceJoinView(ctx, is_dict, quote)
        await view.start()

        # TODO: add as context tutorial
        # await ctx.respond("Start the race by joining it", ephemeral=True)

    async def do_typing_test(self, ctx, is_dict, quote):
        pass

    @staticmethod
    async def do_race(ctx, racers, is_dict, quote):
        """
        racers: dict
        is_dict: bool (if it's a dictionary race)
        quote: list
        """


def setup(bot):
    bot.add_cog(Typing(bot))
