"""
Challenges:
[[a,b,c], a, b] 
"""

from itertools import groupby

from PIL import Image

import icons
from static.badges import get_badge_from_id


class Challenge:
    def __init__(self, *, desc: str, immutable=False):
        self.desc = desc

        # once the challenge is completed, it defaults to to maximum value
        self.immutable = immutable

    async def is_completed(self, ctx, user):
        a, b = await self.progress(ctx, user)
        return a >= b

    async def progress(self, ctx, user):
        a, b = await self.user_progress(ctx, user)

        return a, b

    async def user_progress(ctx, user):
        ...


class Achievement(Challenge):
    def __init__(self, *, name: str, reward=None, **kwargs):
        super().__init__(**kwargs)

        self.name = name
        self.reward = reward

    @property
    def changer(self):
        if self.reward is None:
            return None

        return self.reward.changer

    def in_achievements(self, user):
        return self.name in user.achievements

    async def progress(self, ctx, user):
        a, b = await self.user_progress(ctx, user)

        if self.immutable and self.name in user.achievements:
            a = max(a, b)

        return a, b

    async def user_progress(self, ctx, user):
        return int(self.in_achievements(user)), 1


class Category:
    def __init__(self, *, desc: str, challenges: list, icon: Image = None):
        self.desc = desc
        self.challenges = challenges
        self.icon = icon

    def is_done(self, user):
        return all(
            (e if not isinstance(e, list) else e[-1]).in_achievements(user)
            for e in self.challenges
        )


class Reward:
    def __init__(self, desc):
        self.desc = desc

    def changer(self):
        ...

    @property
    def raw(self):
        ...

    @classmethod
    def group(cls, ins: list):
        ...


class BadgeReward(Reward):
    def __init__(self, badge_id: str):
        self.badge_id = badge_id

        super().__init__(desc=self.get_badge_format(badge_id))

    @property
    def raw(self):
        return get_badge_from_id(self.badge_id)

    @staticmethod
    def get_badge_format(badge_id):
        emoji = get_badge_from_id(badge_id)
        return f"{badge_id.capitalize()} {emoji}"

    def badge_format(self):
        return self.get_badge_format(self.badge_id)

    def changer(self, user):
        if self.badge_id not in user.badges:
            user.badges.append(self.badge_id)

        return user

    @classmethod
    def group(cls, ins: list):
        return [cls.get_badge_format(i.badge_id) for i in ins]


class XPReward(Reward):
    template = f"{icons.xp}" "{} XP"

    def __init__(self, amt: int):
        self.amt = amt

        super().__init__(desc=XPReward.template.format(self.amt))

    @property
    def raw(self):
        return self.amt

    def changer(self, user):
        user.add_xp(self.amt)

        return user

    @classmethod
    def group(cls, ins: list):
        amt = sum(i.amt for i in ins)

        return [cls.template.format(amt)]


def get_in_row(scores, condition):
    if scores == []:
        return 0

    result = [condition(s) for s in scores]

    if result[-1] is False:
        return 0

    return [sum(i) for r, i in groupby(result) if r][-1]
