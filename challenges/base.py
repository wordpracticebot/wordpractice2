"""
Challenges:
[[a,b,c], a, b] 
"""

from itertools import groupby

from PIL import Image


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
            return

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


def get_in_row(scores, condition):
    if scores == []:
        return 0

    result = [condition(s) for s in scores]

    if result[-1] is False:
        return 0

    return [sum(i) for r, i in groupby(result) if r][-1]
