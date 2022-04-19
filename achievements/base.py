"""
Challenges:
[[a,b,c], a, b] 
"""

from PIL import Image

import icons
from static.badges import get_badge_from_id


class Achievement:
    def __init__(self, *, name: str, desc: str, reward=None, immutable=False):
        self.name = name
        self.desc = desc
        self.reward = reward

        # once the achievement is completed, it defaults to to maximum value
        self.immutable = immutable

    @property
    def changer(self):
        if self.reward is None:
            return None

        return self.reward.changer

    def is_completed(self, bot, user):
        a, b = self.progress(bot, user)

        return a >= b

    def progress(self, bot, user):
        a, b = self.user_progress(bot, user)

        if self.immutable and self.name in user.achievements:
            a = max(a, b)

        return a, b

    def user_progress(self, bot, user):
        return int(self.name in user.achievements), 1


class Category:
    def __init__(self, *, desc: str, challenges: list, icon: Image = None):
        self.desc = desc
        self.challenges = challenges
        self.icon = icon

    def is_completed(self, bot, user):
        return all(
            (e if not isinstance(e, list) else e[-1]).is_completed(bot, user)
            for e in self.challenges
        )


class Reward:
    def __init__(self, desc):
        self.desc = desc

    def changer(self):
        ...

    @classmethod
    def group(cls, ins: list):
        ...


class BadgeReward(Reward):
    def __init__(self, badge_id: str):
        self.template = f""
        self.badge_id = badge_id

        super().__init__(desc=self.get_badge_format(badge_id))

    @staticmethod
    def get_badge_format(badge_id):
        emoji = get_badge_from_id(badge_id)
        return f"{emoji} {badge_id.capitalize()}"

    def changer(self, user):
        if self.badge_id not in user.badges:
            user.badges.append(self.badge_id)

        return user

    @classmethod
    def group(self, ins: list):
        return [self.get_badge_format(i.badge_id) for i in ins]


class XPReward(Reward):
    template = f"{icons.xp}" "{} xp"

    def __init__(self, amt: int):
        self.amt = amt

        super().__init__(desc=XPReward.template.format(self.amt))

    def changer(self, user):
        user.add_xp(self.amt)

        return user

    @classmethod
    def group(cls, ins: list):
        amt = sum(i.amt for i in ins)

        return [cls.template.format(amt)]
