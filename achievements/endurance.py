from .base import Achievement, Category


class Endurance(Achievement):
    def __init__(self, name, desc, key, value):
        super().__init__(name, desc)

        self.key = key
        self.value = value

    @staticmethod
    def changer(user):
        user.xp += 10

        return user

    def callback(self, user):
        return self.changer if user[self.key] >= self.value else False

    def progress(self, user):
        return user[self.key], self.value


def generate_endurance(name, key, values, desc):
    return [Endurance(name, desc.format(value), key, value) for value in values]


endurance = Category(
    desc="",
    challenges=[
        generate_endurance(
            "Streakin'",
            "streak",
            (1, 5, 10, 25, 50, 75, 100, 150, 200, 365),
            "Play wordPractice for {} day(s) in a row",
        ),
        generate_endurance(
            "Democracy!",
            "votes",
            (1, 5, 10, 25, 50, 100, 250, 500, 750, 1000),
            "Vote for wordPractice {} time(s)",
        ),
    ],
)
