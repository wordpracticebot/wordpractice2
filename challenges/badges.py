from static.assets import badge_icon

from .base import Achievement, Category


class Badges(Achievement):
    def __init__(self, name, amt):
        super().__init__(
            name=name,
            desc="Earn {} badge{}".format(amt, "s" if amt > 1 else ""),
        )

        self.amt = amt

    async def user_progress(self, ctx, user):
        return len(user.badges), self.amt


class Collector(Achievement):
    def __init__(self):
        super().__init__(
            name="Collector", desc="Earn every badge in a season", immutable=True
        )

    async def user_progress(self, ctx, user):
        season_info = await ctx.bot.mongo.get_season_info()

        badges = season_info["badges"]

        return len(set(badges) & set(user.badges)), len(badges)


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
    reward=None,
)
