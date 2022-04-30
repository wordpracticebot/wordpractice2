from functools import lru_cache

from .base import Achievement, BadgeReward, XPReward


@lru_cache(maxsize=1)
async def get_season_challenges_from_unix(bot, unix_time):
    ...


async def get_season_challenges(bot):
    unix_time = ...

    return get_season_challenges_from_unix(bot, unix_time)


all_season_challenges = []
