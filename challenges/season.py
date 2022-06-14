from .rewards import BadgeReward


async def get_season_tiers(bot):
    season_info = await bot.mongo.get_season_info()

    if season_info is None or season_info["enabled"] is False:
        return

    for i, badge_id in enumerate(season_info["badges"]):
        yield (i + 1) * 40000, BadgeReward(badge_id)


async def check_season_rewards(bot, user):
    async for v, r in get_season_tiers(bot):
        if user.xp >= v > user.last_season_value:
            yield v, r
