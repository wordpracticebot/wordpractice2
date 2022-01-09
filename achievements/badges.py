from .base import Achievement, Category


class Badges(Achievement):
    def __init__(self, name, amt):
        super().__init__(name, f"Earn {amt} badges", "Get some coins")

        self.amt = amt

    @staticmethod
    def changer(user):
        user.xp += 10

        return user

    def callback(self, user):
        return self.changer if len(user.badges) >= self.amt else False

    def progress(self, user):
        return len(user.badges), self.amt


badges = Category(
    desc="",
    challenges=[
        [
            Badges("First Badge", 1),
            Badges("Badge Enthusiast", 10),
            Badges("Badge Collector", 20),
            Badges("Badge Hoarder", 30),
            Badges("Badge Exporter", 50),
            Badges("Badge Tycoon", 100),
        ]
    ],
)
