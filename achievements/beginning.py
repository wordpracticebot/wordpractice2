from .base import Achievement, Category


class StartingOut(Achievement):
    def __init__(self):
        super().__init__("Starting out", "Use wordPractice for the first time")

    def callback(self, user):
        return bool(user)


beginning = Category(
    desc="",
    challenges=[StartingOut()],
)
