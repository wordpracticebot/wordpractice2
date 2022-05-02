from .base import BadgeReward


async def get_season_challenges(bot):
    season_info = await bot.mongo.get_season_info()

    for i, badge_id in enumerate(season_info["badges"]):
        yield (i + 1) * 15000, BadgeReward(badge_id)
