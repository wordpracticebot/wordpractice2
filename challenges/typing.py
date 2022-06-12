from helpers.utils import calculate_score_consistency
from static.assets import speed_icon

from .base import Achievement, Category, get_in_row


class Speed(Achievement):
    def __init__(self, name, wpm):
        super().__init__(name=name, desc=f"Type {wpm} wpm")

        self.wpm = wpm

    async def progress(self, ctx, user):
        return user.highest_speed, self.wpm


class OverflowSpeed(Speed):
    def __init__(self, name, wpm):
        super().__init__(
            name,
            wpm,
        )


class Perfectionist(Achievement):
    def __init__(self, amt):
        super().__init__(
            name="Perfectionist",
            desc=f"Complete {amt} typing tests in a row with 100% accuracy.",
        )

        self.amt = amt

    async def progress(self, ctx, user):
        return get_in_row(user.scores, lambda s: s.acc == 100), self.amt


class Consistency(Achievement):
    def __init__(self):
        super().__init__(
            name="Consistency",
            desc="Complete 30 typing tests in a row with 90%+ consistency",
        )

    async def progress(self, ctx, user):
        result = (
            0
            if len(user.scores) < 30
            else calculate_score_consistency(user.scores[-30:])
        )

        return result, 90


class BeepBoop(Achievement):
    def __init__(self, amt):
        super().__init__(
            name="Beep Boop",
            desc=f"Complete {amt} tests in a row at exactly 60 wpm (±1 wpm)",
        )

        self.amt = amt

    async def progress(self, ctx, user):
        return get_in_row(user.scores, lambda s: abs(s.wpm - 60) <= 1), self.amt


typing = Category(
    desc="Typing related achievements",
    challenges=[
        [
            [
                Speed("Beginner Typist", 60),
                Speed("Amateur Typist", 80),
                Speed("Proficient Typist", 100),
                Speed("Fast Typist", 120),
                Speed("Pro Typist", 150),
            ],
            [
                Speed("Crazy Typist", 180),
                Speed("200 Barrier", 200),
                Speed("Steno?", 220),
                Speed("Cheating?", 240),
            ],
        ],
        [
            [Perfectionist(amt) for amt in [10, 25, 50, 100]],
        ],
        Consistency(),
        [
            [BeepBoop(amt) for amt in [3, 5, 10, 15]],
        ],
    ],
    icon=speed_icon,
)
