from .base import Achievement, Category, XPReward


# TODO: add proper rewards and descriptions for all achievements
class Speed(Achievement):
    def __init__(self, name, wpm):
        super().__init__(name, f"Type {wpm} wpm", XPReward(5000))

        self.wpm = wpm

    def callback(self, user):
        return self.changer if user.highest_speed >= self.wpm else False

    def progress(self, user):
        return user.highest_speed, self.wpm


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
