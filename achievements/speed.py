from .base import Achievement, Category


def highest_speed(user):
    if user.highspeed == {}:
        return 0
    return max([s.wpm for s in user.highspeed.values()])


# TODO: add proper rewards and descriptions for all achievements
class Speed(Achievement):
    def __init__(self, name, wpm):
        super().__init__(name, f"Type {wpm} wpm", "Get some xp")

        self.wpm = wpm

    @staticmethod
    def changer(user):
        user.xp += 10

        return user

    def callback(self, user):
        return self.changer if highest_speed(user) >= self.wpm else False

    def progress(self, user):
        return highest_speed(user), self.wpm


speed = Category(
    desc="",
    challenges=[
        [
            Speed("Beginner Typist", 60),
            Speed("Amateur Typist", 80),
            Speed("Proficient Typist", 100),
            Speed("Fast Typist", 120),
            Speed("Pro Typist", 150),
            Speed("Crazy Typist", 180),
            Speed("200 Barrier", 200),
            Speed("Steno?", 220),
            Speed("Cheating?", 240),
        ]
    ],
)
