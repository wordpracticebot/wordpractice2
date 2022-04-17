from itertools import groupby

from static.assets import endurance_icon

from .base import Achievement, Category


class SingleStatEndurance(Achievement):
    def __init__(self, name, desc, key, value):
        super().__init__(name, desc)

        self.key = key
        self.value = value

    def callback(self, user):
        return self.changer if user[self.key] >= self.value else False

    def progress(self, user):
        return user[self.key], self.value


def generate_single_stat_endurance(name, key, values, desc):
    return [
        SingleStatEndurance(
            name, desc.format(value, "s" if value > 1 else ""), key, value
        )
        for value in values
    ]


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


endurance = Category(
    desc="",
    challenges=[
        generate_single_stat_endurance(
            "Streakin'",
            "streak",
            (1, 5, 10, 25, 50, 75, 100, 150, 200, 365),
            "Play wordPractice for {} day{} in a row",
        ),
        generate_single_stat_endurance(
            "Democracy!",
            "votes",
            (1, 5, 10, 25, 50, 100, 200, 350, 500, 750),
            "Vote for wordPractice {} time{}",
        ),
        [Perfectionist(amt) for amt in [10, 25, 50, 100, 250, 500]],
    ],
    icon=endurance_icon,
)
