from itertools import groupby

from helpers.utils import calculate_score_consistency
from static.assets import speed_icon

from .base import Achievement, Category, XPReward


def get_in_row(scores, condition):
    if scores == []:
        return 0

    result = [condition(s) for s in scores]

    if result[-1] is False:
        return 0

    return [sum(i) for r, i in groupby(result) if r][-1]


# TODO: add proper rewards and descriptions for all achievements
class Speed(Achievement):
    def __init__(self, name, wpm):
        super().__init__(name=name, desc=f"Type {wpm} wpm", reward=XPReward(5000))

        self.wpm = wpm

    async def user_progress(self, ctx, user):
        return user.highest_speed, self.wpm


class Perfectionist(Achievement):
    def __init__(self, amt):
        super().__init__(
            name="Perfectionist",
            desc=f"Complete {amt} typing tests in a row with 100% accuracy.",
        )

        self.amt = amt

    async def user_progress(self, ctx, user):
        return get_in_row(user.scores, lambda s: s.acc == 100), self.amt


class Consistency(Achievement):
    def __init__(self):
        super().__init__(
            name="Consistency",
            desc="Complete 30 typing tests in a row with an consistency of 90%+",
            immutable=True,
        )

    async def user_progress(self, ctx, user):
        result = (
            0
            if len(user.scores) < 30
            else calculate_score_consistency(user.scores[:30])
        )

        return result, 30


class BeepBoop(Achievement):
    def __init__(self, amt):
        super().__init__(
            name="Beep Boop",
            desc=f"Complete {amt} tests in a row at exactly 60 wpm (give or take <1 wpm)",
            immutable=True,
        )

        self.amt = amt

    async def user_progress(self, ctx, user):
        return get_in_row(user.scores, lambda s: int(s.wpm) == 60), self.amt


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
        Consistency(),
        [BeepBoop(amt) for amt in [3, 7, 13, 20]],
    ],
    icon=speed_icon,
)
