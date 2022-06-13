from static.assets import badge_icon

from .base import Achievement, Category
from .rewards import BadgeReward


class Badges(Achievement):
    def __init__(self, name, amt):
        super().__init__(
            name=name,
            desc="Earn {} badge{}".format(amt, "s" if amt > 1 else ""),
        )

        self.amt = amt

    async def progress(self, ctx, user):
        return len(user.badges), self.amt


class Collector(Achievement):
    def __init__(self):
        super().__init__(name="Collector", desc="Earn every badge in a season")

    async def progress(self, ctx, user):
        season_info = await ctx.bot.mongo.get_season_info()

        if season_info["enabled"] and len(season_info["badges"]) > 0:
            badges = season_info["badges"]
            progress = len(set(badges) & set(user.badges))

        else:
            progress = 0

        return progress, len(badges)


badges = Category(
    desc="Badge related achievements",
    challenges=[
        [
            [
                Badges("First Badge", 1),
                Badges("Badge Enthusiast", 5),
                Badges("Badge Collector", 10),
                Badges("Badge Hoarder", 25),
            ],
            [
                Badges("Badge Exporter", 50),
                Badges("Badge Tycoon", 100),
            ],
        ],
        Collector(),
    ],
    icon=badge_icon,
    reward=BadgeReward("gold_badge"),
)
