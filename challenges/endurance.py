from datetime import datetime

from bot import Context
from static.assets import endurance_icon

from .base import Achievement, Category
from .rewards import BadgeReward


class SingleStatEndurance(Achievement):
    def __init__(self, name, desc, key, value):
        super().__init__(name=name, desc=desc)

        self.key = key
        self.value = value

    async def progress(self, ctx: Context, user):
        return user[self.key], self.value

    @classmethod
    def generate(cls, name, key, values, desc):
        return [
            [cls(name, desc.format(v, "s" if v > 1 else ""), key, v) for v in value]
            for value in values
        ]


class Veteran(Achievement):
    def __init__(self, days):
        super().__init__(
            name="Veteran", desc=f"Be a wordPractice member for {days} days"
        )

        self.days = days

    @staticmethod
    def get_account_days(user):
        now = datetime.utcnow()

        return (now - user.created_at).days

    async def progress(self, ctx: Context, user):
        return self.get_account_days(user), self.days


class Birthday(Achievement):
    def __init__(self):
        super().__init__(
            name="Birthday",
            desc="Use wordPractice on the day it was created (August 12)",
        )

    async def progress(self, ctx: Context, user):
        now = datetime.utcnow()

        return int(now.month == 8 and now.day == 12), 1


endurance = Category(
    desc="Endurance based achievements",
    challenges=[
        SingleStatEndurance.generate(
            "Streakin'",
            "streak",
            ((1, 5, 10, 25, 50, 75, 100), (150, 365)),
            "Play wordPractice for {} day{} in a row",
        ),
        SingleStatEndurance.generate(
            "Democracy!",
            "votes",
            ((1, 5, 10, 25, 50, 100, 200, 300), (500, 750)),
            "Vote for wordPractice {} time{}",
        ),
        [
            [Veteran(days) for days in [7, 14, 30, 90, 180, 365]],
        ],
        Birthday(),
    ],
    icon=endurance_icon,
    reward=BadgeReward("thomas"),
)
