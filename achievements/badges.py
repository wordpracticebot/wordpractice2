from static.assets import badge_icon

from .base import Achievement, Category, XPReward


class Badges(Achievement):
    def __init__(self, name, amt):
        super().__init__(
            name,
            "Earn {} badge{}".format(amt, "s" if amt > 1 else ""),
            XPReward(2000),
        )

        self.amt = amt

    def callback(self, user):
        return self.changer if len(user.badges) >= self.amt else False

    def progress(self, user):
        return len(user.badges), self.amt


badges = Category(
    desc="",
    challenges=[
        [
            Badges("First Badge", 1),
            Badges("Badge Enthusiast", 5),
            Badges("Badge Collector", 10),
            Badges("Badge Hoarder", 20),
            Badges("Badge Exporter", 50),
            Badges("Badge Tycoon", 100),
        ]
    ],
    icon=badge_icon,
)
