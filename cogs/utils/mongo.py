import pickle
import time
from datetime import datetime
from typing import Union

import discord
import pymongo
from cache import AsyncTTL
from discord.ext import commands
from discord.utils import escape_markdown
from motor.motor_asyncio import AsyncIOMotorClient
from umongo import Document, EmbeddedDocument, exceptions
from umongo.fields import (
    BooleanField,
    DateTimeField,
    DictField,
    EmbeddedField,
    FloatField,
    IntegerField,
    ListField,
    StringField,
)
from umongo.frameworks import MotorAsyncIOInstance

import data.icons as icons
from bot import Context, WordPractice
from challenges.rewards import BadgeReward
from config import DATABASE_NAME, DATABASE_URI
from data.constants import (
    AUTO_MODERATOR_NAME,
    CHALLENGE_AMT,
    DEFAULT_THEME,
    LIGHT_SAVE_AMT,
    PREMIUM_LAUNCHED,
    PREMIUM_PLUS_SAVE_AMT,
    PREMIUM_SAVE_AMT,
    SCORE_SAVE_AMT,
    TEST_ZONES,
    VOTING_SITES,
)
from helpers.ui import get_log_embed
from helpers.user import get_24h_stat
from helpers.utils import datetime_to_unix, get_test_type
from static.badges import get_badge_from_id


def _get_meta_data(user):
    return {
        "id": user.id,
        "name": user.name,
        "discriminator": user.discriminator,
        "avatar": user.avatar,
        "created_at": user.created_at,
        "infractions": user.infractions,
        "banned": user.banned,
    }


class Infraction(EmbeddedDocument):
    mod_name = StringField(required=True)  # NAME#DISCRIMINATOR
    mod_id = IntegerField(require=True)

    is_ban = BooleanField(required=True)  # True = ban, False = unban

    reason = StringField(required=True)

    timestamp = DateTimeField(required=True)

    @property
    def unix_timestamp(self):
        return datetime_to_unix(self.timestamp)

    @property
    def name(self):
        return "Ban" if self.is_ban else "Unban"


class Score(EmbeddedDocument):
    wpm = FloatField(default=0.0)
    raw = FloatField(default=0.0)
    acc = FloatField(default=0.0)

    # correct words
    cw = IntegerField(default=0)
    # total words
    tw = IntegerField(default=0)

    xp = IntegerField(default=0)
    timestamp = DateTimeField(default=datetime.min)

    wrong = ListField(StringField, default=[])

    is_race = BooleanField(default=False)
    is_hs = BooleanField(default=False)

    test_type_int = IntegerField(default=0)

    @property
    def unix_timestamp(self):
        return datetime_to_unix(self.timestamp)

    @property
    def test_type(self):
        test_prefix = get_test_type(self.test_type_int, self.cw)

        test_suffix = "Race" if self.is_race else "Test"

        return f"{test_prefix} {test_suffix}"


class PremiumMembership(EmbeddedDocument):
    expire_date = DateTimeField(required=True)
    name = StringField(required=True)

    @property
    def is_expired(self):
        return self.expire_date < datetime.now()

    @property
    def int_id(self):
        return (
            1
            if self.name == "Light"
            else 2
            if self.name == "Premium"
            else 3
            if self.name == "Premium+"
            else 0
        )

    @property
    def save_amt(self):
        if self.int_id == 1:
            return LIGHT_SAVE_AMT

        if self.int_id == 2:
            return PREMIUM_SAVE_AMT

        if self.int_id == 3:
            return PREMIUM_PLUS_SAVE_AMT

        return SCORE_SAVE_AMT

    @property
    def icon(self):
        if self.int_id == 1:
            return icons.light_sub

        if self.int_id == 2:
            return icons.premium_sub

        if self.int_id == 3:
            return icons.premium_plus_sub

        return ""

    @property
    def export_scores(self):
        return self.int_id in [2, 3]

    @property
    def reduced_cooldowns(self):
        return self.int_id in [2, 3]

    @property
    def view_heat_map(self):
        return self.int_id == 3


class UserBase(Document):
    class Meta:
        abstract = True

    # General member information
    id = IntegerField(attribute="_id")
    name = StringField(required=True)
    discriminator = IntegerField(required=True)
    avatar = StringField(default=None)
    created_at = DateTimeField(required=True)
    premium = EmbeddedField(PremiumMembership, default=None)

    # list of commands that the user has run before (for context tutorials)
    # includes subcommands from groups
    cmds_run = ListField(StringField, default=[])

    # Statistics
    words = IntegerField(default=0)

    # Season
    xp = IntegerField(default=0)

    # Challenge
    daily_completion = ListField(BooleanField, default=[False] * CHALLENGE_AMT)
    last_season_value = IntegerField(default=0)  # value of the last season completion

    # 24 Hour
    raw_words_24h = ListField(IntegerField, default=[])
    raw_xp_24h = ListField(IntegerField, default=[])

    last_24h_save = DateTimeField(default=datetime.min)

    # Daily
    test_amt = IntegerField(default=0)  # amount of tests in the last day

    # Typing
    highspeed = DictField(StringField(), EmbeddedField(Score), required=True)
    scores = ListField(EmbeddedField(Score), default=[])

    # Other statistics
    achievements = DictField(
        StringField(), ListField(DateTimeField), default=[]
    )  # id: timestamp
    trophies = ListField(
        IntegerField, default=[0, 0, 0, 0]
    )  # [first, second, third, top 10]

    # Cosmetics
    badges = ListField(StringField, default=[])
    status = StringField(default="")

    # Streak of playing
    streak = IntegerField(default=0)  # days
    highest_streak = IntegerField(default=0)
    last_streak = DateTimeField(required=True)  # not last bot usage time

    # Voting
    votes = IntegerField(default=0)

    last_voted = DictField(
        StringField(),
        DateTimeField(),
        default={name: datetime.min for name in VOTING_SITES.keys()},
    )

    # Infractions
    infractions = ListField(EmbeddedField(Infraction), default=[])
    banned = BooleanField(default=False)

    # Settings
    theme = ListField(StringField, default=DEFAULT_THEME)
    language = StringField(default="english")
    level = StringField(default="easy")
    pacer_speed = StringField(default="")  # "", "avg", "pb", "INTEGER"
    pacer_type = IntegerField(default=0)  # 0 = horizontal, 1 = vertical


class User(UserBase):
    class Meta:
        collection_name = "users"

    @property
    def unix_created_at(self):
        return datetime_to_unix(self.created_at)

    @property
    def status_emoji(self):
        return get_badge_from_id(self.status) or ""

    @property
    def badge_objs(self):
        return [BadgeReward(b) for b in self.badges]

    @property
    def avatar_url(self):
        return f"https://cdn.discordapp.com/avatars/{self.id}/{self.avatar}"

    @property
    def username(self):
        return escape_markdown(f"{self.name}#{self.discriminator}")

    @property
    def display_name(self):
        icon_display = f"{self.icon} " if self.icon else ""
        status_display = f" {self.status_emoji}" if self.status else ""

        return f"{icon_display}{self.username}{status_display}"

    @property
    def words_24h(self):
        return get_24h_stat(self.raw_words_24h, self.last_24h_save)

    @property
    def xp_24h(self):
        return get_24h_stat(self.raw_xp_24h, self.last_24h_save)

    @property
    def is_premium(self):
        if PREMIUM_LAUNCHED is False:
            return True

        if self.premium is not None and not self.premium.is_expired:
            return True

        return False

    @property
    def save_amt(self):
        return self.premium.save_amt if self.is_premium else SCORE_SAVE_AMT

    @property
    def icon(self):
        return self.premium.icon if self.is_premium else ""

    @property
    def export_scores(self):
        return self.premium.export_scores if self.is_premium else False

    @property
    def view_heat_map(self):
        if self.is_premium:
            return self.premium.view_heat_map

        return False

    @property
    def is_daily_complete(self):
        return all(self.daily_completion)

    @property
    def highest_speed(self):
        return max(s.wpm for s in self.highspeed.values())

    def add_24h_stats(self, xp: int = 0, words: int = 0):
        new_words_24h = self.words_24h
        new_xp_24h = self.xp_24h

        if new_words_24h != self.raw_words_24h or new_xp_24h != self.raw_xp_24h:
            self.last_24h_save = datetime.utcnow()

        new_xp_24h[-1] += xp
        new_words_24h[-1] += words

        self.raw_words_24h = new_words_24h
        self.raw_xp_24h = new_xp_24h

    def add_words(self, words: int):
        self.words += words

        self.add_24h_stats(words=words)

    def add_xp(self, xp: int):
        self.xp += xp

        self.add_24h_stats(xp=xp)

    def add_score(self, score: Score):
        if len(self.scores) >= self.save_amt:
            del self.scores[: len(self.scores) - self.save_amt + 1]

        self.scores.append(score)

    def add_badge(self, badge_id):
        if badge_id not in self.badges:
            # Setting as status if it's their first badge
            if len(self.badges) == 0:
                self.status = badge_id

            self.badges.append(badge_id)


# Backup for users that have been wiped
class UserBackup(UserBase):
    wiped_at = DateTimeField(required=True)

    class Meta:
        collection_name = "backup"

    @property
    def unix_wiped_at(self):
        return datetime_to_unix(self.wiped_at)


class Tournament(Document):
    name = StringField(required=True)
    description = StringField(required=True)

    link = StringField(required=True)
    icon = StringField(required=True)

    start_time = DateTimeField(required=True)
    end_time = DateTimeField(required=True)

    unit = StringField(required=True)

    prizes = ListField(StringField, default=[])

    normal_test = BooleanField(required=True)

    async def get_rankings(self, bot: WordPractice):
        ...

    async def get_score(self, bot: WordPractice, user_id: int):
        ...

    @property
    def ranking_size(self) -> int:
        ...

    @property
    def rules(self):
        ...

    @property
    def unix_start(self):
        return datetime_to_unix(self.start_time)

    @property
    def unix_end(self):
        return datetime_to_unix(self.end_time)

    def get_value(self, score: Score):
        return score.wpm

    def get_ranking_prefix(self, placing: int, value: int) -> str:
        # 1 is the highest placing
        ...


class QualificationTournament(Tournament):
    unit = StringField(default="wpm")
    normal_test = BooleanField(default=False)

    # Amount of users allowed to qualify for the tournament
    amount = IntegerField(required=True)

    bracket_start_time = DateTimeField(required=True)

    host_server = StringField(required=True)
    host_server_invite = StringField(required=True)

    rankings = DictField(IntegerField(), IntegerField(), default={})

    async def get_rankings(self, bot: WordPractice):
        return self.rankings

    async def get_score(self, bot: WordPractice, user_id: int):
        return self.rankings.get(str(user_id), None)

    @property
    def ranking_size(self) -> int:
        return len(self.rankings)

    @property
    def unix_bracket_start(self):
        return datetime_to_unix(self.bracket_start_time)

    @property
    def rules(self):
        invite = f"https://discord.gg/{self.host_server_invite}"
        return (
            f"The participants with the top {self.amount} highest scores qualify.\n\n"
            f"A bracket will be hosted on **<t:{self.unix_bracket_start}:f>** on the **[{self.host_server} server]({invite})** to determine the winner from those that qualify.\n\n"
            "**__Make sure to join the [server]({invite}) if your participate.__**"
        )

    def get_ranking_prefix(self, placing: int, _) -> str:
        if placing <= self.amount:
            return icons.green_dot

        return icons.red_dot


class ActivityTournament(Tournament):
    unit = StringField(default="xp")
    normal_test = BooleanField(default=True)

    category = IntegerField(required=True)
    stat = IntegerField(required=True)

    winners = IntegerField(required=True)

    lb_size = IntegerField(required=True)

    initial_rankings = DictField(StringField(), IntegerField(), default={})
    final_rankings = DictField(StringField(), IntegerField(), default={})

    async def get_rankings(self, bot: WordPractice):
        if self.final_rankings:
            lb = self.final_rankings
        else:
            lb = (
                await bot.lbs[self.category]
                .stats[self.stat]
                .get_lb_data(end=self.lb_size)
            )

        return {key: lb[key] - self.initial_rankings.get(str(key), 0) for key in lb}

    async def get_score(self, bot: WordPractice, user_id: int):
        score = await bot.redis.zscore(f"lb.{self.category}.{self.stat}", user_id)

        if not score:
            return None

        return score - self.initial_rankings.get(str(user_id), 0)

    @property
    def ranking_size(self) -> int:
        return self.lb_size

    def get_ranking_prefix(self, placing: int, _) -> str:
        if placing <= self.winners:
            return icons.green_dot

        return icons.red_dot

    @property
    def rules(self):
        return "Earn as much XP as you can by completing typing tests."


class Mongo(commands.Cog):
    def __init__(self, bot: WordPractice):
        self.bot = bot
        self.db = AsyncIOMotorClient(DATABASE_URI, io_loop=bot.loop)[DATABASE_NAME]

        instance = MotorAsyncIOInstance(self.db)

        g = globals()

        for n in (
            "Infraction",
            "Score",
            "PremiumMembership",
            "UserBase",
            "User",
            "UserBackup",
            "Tournament",
            "QualificationTournament",
            "ActivityTournament",
        ):
            setattr(self, n, instance.register(g[n]))
            getattr(self, n).bot = bot

    def get_auto_mod(self, mod):
        if mod is None:
            mod = AUTO_MODERATOR_NAME
            mod_id = self.bot.user.id
        else:
            mod_id = mod.id
            mod = str(mod)

        return mod, mod_id

    async def get_user_from_cache(self, user_id: int):
        u = await self.bot.redis.hget("user", user_id)

        if u is not None:
            u = self.User.build_from_mongo(pickle.loads(u))

        return u

    @property
    def default_score(self):
        # Schemas are instantiated when mongo cog is initialized
        # Default scores must be passed in at initialization to access schema
        score = dict(self.Score.schema.as_marshmallow_schema()().load({}))

        return {s: score for s in TEST_ZONES.keys()}

    async def fetch_all_tournaments(self):
        # Fetching the tournament data from teh database
        data = self.bot.mongo.Tournament.find()

        return [d async for d in data]

    async def fetch_many_users(self, *user_ids):
        if not user_ids:
            return {}

        data = {}
        not_found = set()

        # Trying to get as many users as posisble from the cache
        users = await self.bot.redis.hmget("user", *user_ids)

        for _id, u in zip(user_ids, users):
            _id = int(_id)

            if u is None:
                not_found.add(int(_id))
            else:
                data[_id] = self.User.build_from_mongo(pickle.loads(u))

        if not_found:
            # Fetching the rest of the users from the database
            cursor = self.User.find({"id": {"$in": list(not_found)}})

            fetched_users = {u.id: u async for u in cursor}

            self.bot.dispatch("cache_fetched_users", fetched_users)

            data.update(fetched_users)

        return data

    @commands.Cog.listener()
    async def on_cache_fetched_users(self, fetched_users):
        raw_fetched_users = {
            _id: pickle.dumps(u.to_mongo()) for _id, u in fetched_users.items()
        }

        await self.bot.redis.hmset("user", raw_fetched_users)

    async def fetch_user(
        self, user: Union[discord.User, int, tuple[str, str]], create=False
    ):
        # User id
        if isinstance(user, int):
            return await self.fetch_user_from_query({"id": user}, user_id=user)

        # name#discriminator
        elif isinstance(user, (list, tuple)):
            return await self.fetch_user_from_query(
                {"name": user[0], "discriminator": user[1]}
            )

        # User object
        else:
            return await self.fetch_user_from_query(
                {"id": user.id}, user_id=user.id, user=user, create=create
            )

    async def fetch_user_from_query(
        self,
        query: dict,
        *,
        user_id: int = None,
        user: discord.User = None,
        create: bool = False,
    ) -> Union[User, None]:

        if user_id is None:
            u = None
        else:
            # Checking if the user is in the cache
            u = await self.get_user_from_cache(user_id)

        if u is None:
            u = await self.User.find_one(query)

            if u is None:
                if user is not None and not user.bot:
                    if create is False:
                        return u

                    u = self.User(
                        id=user.id,
                        name=user.name,
                        discriminator=user.discriminator,
                        avatar=user.avatar.key if user.avatar else None,
                        highspeed=self.default_score,
                        created_at=datetime.utcnow(),
                        last_streak=datetime.utcnow(),
                    )

                    await self.replace_user_data(u)
                    return u

                return

        uj = u.to_mongo()

        if user is not None:
            current = self.get_current(user)

            # Checking if user info needs to be updated
            if current.values() != [u.name, u.discriminator, u.avatar]:
                await self.update_user(user.id, {"$set": current})
                uj.update(current)

            u = self.User.build_from_mongo(uj)

        # Updating in cache
        await self.bot.redis.hset("user", u.id, pickle.dumps(uj))

        return u

    def get_current(self, user):
        return {
            "name": user.name,
            "discriminator": user.discriminator,
            "avatar": user.avatar.key if user.avatar else None,
        }

    async def wipe_user(self, user, mod: Union[discord.Member, discord.User] = None):
        mod, mod_id = self.get_auto_mod(mod)

        timestamp = round(time.time())

        embed = self.bot.error_embed(
            title="Account Wiped",
            description=(
                f"**User:** {user.username}\n"
                f"**User ID:** {user.id}\n"
                f"**Moderator:** {mod} ({mod_id})\n"
                f"**Timestamp:** <t:{timestamp}:R>"
            ),
        )
        await self.bot.impt_wh.send(embed=embed)

        # Saving a backup in the database

        backup = await self.UserBackup.find_one({"id": user.id})

        # TODO: replace the data instead of deleting
        if backup is not None:
            await backup.delete()

        # Building object from_mongo does not work when trying to commit
        backup = self.UserBackup(**user.dump(), wiped_at=datetime.utcnow())

        try:
            await backup.commit()
        except pymongo.errors.DuplicateKeyError:
            pass

        # Resetting the user's data

        meta_data = _get_meta_data(user)

        # Resetting the user's account
        new_data = self.User(
            **meta_data,
            last_streak=datetime.utcnow(),
            highspeed=self.default_score,
        )

        for field, value in new_data.dump().items():
            if field not in meta_data:
                user[field] = value

        await self.replace_user_data(user)

        # Removing the user from the leaderboard
        for lb in self.bot.lbs:
            for stat in lb.stats:
                await stat.remove_user(user.id)

    async def restore_user(self, user):
        backup = await self.UserBackup.find_one({"id": user.id})

        if backup is None:
            return False

        meta_data = _get_meta_data(user)

        backup_data = backup.dump()
        del backup_data["wiped_at"]

        for field, value in backup_data.items():
            if field not in meta_data:
                user[field] = value

        return user, backup

    async def update_user(self, user, query: dict):
        if isinstance(user, int):
            user_id = user
        else:
            user_id = user.id

        await self.db.users.update_one({"_id": user_id}, query)

        await self.bot.redis.hdel("user", user_id)

    async def replace_user_data(self, new_user, member=None):
        if member is not None:
            current = self.get_current(member)

            new_user.update(current)

        try:
            await new_user.commit()
        except pymongo.errors.DuplicateKeyError:
            pass
        except exceptions.UpdateError:
            await self.bot.redis.hdel("user", new_user.id)
        else:
            # Caching new user data
            await self.bot.redis.hset(
                "user", new_user.id, pickle.dumps(new_user.to_mongo())
            )

    @AsyncTTL(time_to_live=10 * 60, maxsize=32)
    async def get_info_data(self, info_id: str):
        return await self.db.info.find_one({"_id": info_id})

    async def get_season_info(self):
        """
        Schema:

        enabled: bool
        badges: list[str]
        """
        return await self.get_info_data("season-info")

    async def get_announcements(self):
        raw_data = await self.get_info_data("announcements")

        return raw_data["data"]

    async def add_inf(
        self, ctx: Context, user, user_data, reason, mod=None, is_ban: bool = True
    ):
        """Doesn't update in the database"""

        mod, mod_id = self.get_auto_mod(mod)

        inf = self.Infraction(
            mod_name=mod,
            mod_id=mod_id,
            is_ban=is_ban,
            reason=reason,
            timestamp=datetime.utcnow(),
        )

        user_data.infractions.append(inf)
        user_data.banned = is_ban

        # Logging the infraction
        embed = get_log_embed(
            ctx,
            title=f"User {inf.name}ned",  # sorry
            additional=f"**Moderator:** {mod} ({mod_id})\n**Reason:** {reason}",
            error=True,
            author=user,
        )

        await self.bot.impt_wh.send(embed=embed)

        return user_data


def setup(bot: WordPractice):
    bot.add_cog(Mongo(bot))
