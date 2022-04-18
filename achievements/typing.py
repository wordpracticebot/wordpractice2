from itertools import groupby

from static.assets import speed_icon

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


class Perfectionist(Achievement):
    def __init__(self, amt):
        super().__init__(
            "Perfectionist",
            f"Complete {amt} typing tests in a row with 100% accuracy.",
        )

        self.amt = amt

    def callback(self, user):
        return self.changer if self.get_scores_in_a_row(user) >= self.amt else False

    def progress(self, user):
        return self.get_scores_in_a_row(user), self.amt

    @staticmethod
    def get_scores_in_a_row(user):
        if user.scores == []:
            return 0

        result = [s.acc == 100 for s in user.scores]

        if result[-1] is False:
            return 0

        return [sum(i) for r, i in groupby(result) if r][-1]


typing = Category(
    desc="Typing related achievements",
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
        ],
        [Perfectionist(amt) for amt in [10, 25, 50, 100, 250, 500]],
    ],
    icon=speed_icon,
)
