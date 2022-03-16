"""
callback -> 

True = finished but no state change
False = not finished
Callable[[dict], dict] = state change
"""

"""
Challenges:
[[a,b,c], a, b] 
"""

import icons
from static.badges import get_badge_from_id


class Achievement:
    def __init__(self, name: str, desc: str, reward=None):
        self.name = name
        self.desc = desc
        self.reward = reward

    @property
    def changer(self):
        if self.reward is None:
            return True

        return self.reward.changer

    def progress(self, user) -> tuple:
        return int(self.name in user.achievements), 1

    def has_callback(self):
        return callable(getattr(self.__class__, "callback", False))


class Category:
    def __init__(self, desc: str, challenges: list):
        self.desc = desc
        self.challenges = challenges

    def is_completed(self, user):
        return all(
            (lambda m: m[0] >= m[1])(
                (e if not isinstance(e, list) else e[-1]).progress(user)
            )
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
        user.xp += self.amt

        return user

    @classmethod
    def group(cls, ins: list):
        amt = sum(i.amt for i in ins)

        return [cls.template.format(amt)]
