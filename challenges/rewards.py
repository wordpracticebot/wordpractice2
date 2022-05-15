from collections import defaultdict

import icons
from static.badges import get_badge_from_id


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
        user.add_badge(self.badge_id)

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


def group_rewards(rewards: list):
    # Grouping the rewards by type
    groups = defaultdict(list)

    for r in rewards:
        groups[type(r)].append(r)

    r_overview = []

    for g_type, g in groups.items():
        r_overview += g_type.group(g)

    return r_overview
