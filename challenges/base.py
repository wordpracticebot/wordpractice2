"""
Challenges:
[[a,b,c], a, b] 
"""

from itertools import groupby

from PIL import Image


class Challenge:
    def __init__(self, *, desc: str):
        self.desc = desc

    async def is_completed(self, ctx, user):
        a, b = await self.progress(ctx, user)

        return a >= b

    async def progress(ctx, user):
        ...


class Achievement(Challenge):
    def __init__(self, *, name: str, **kwargs):
        super().__init__(**kwargs)

        self.name = name

    def in_achievements(self, user):
        return self.name in user.achievements

    async def progress(self, ctx, user):
        return int(self.in_achievements(user)), 1


class Category:
    def __init__(self, *, desc: str, challenges: list, reward=None, icon: Image = None):
        self.desc = desc
        self.icon = icon

        self.challenges = challenges

        self.reward = reward

    @property
    def changer(self):
        if self.reward is None:
            return

        return self.reward.changer


def get_in_row(scores, condition):
    if scores == []:
        return 0

    result = [condition(s) for s in scores]

    if result[-1] is False:
        return 0

    return [sum(i) for r, i in groupby(result) if r][-1]
