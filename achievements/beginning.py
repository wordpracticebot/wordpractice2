from static.assets import beginning_icon

from .base import Achievement, Category


class StartingOut(Achievement):
    def __init__(self):
        super().__init__(
            name="Starting out", desc="Use wordPractice for the first time"
        )

    def user_progress(self, bot, user):
        return int(bool(user)), 1


class Quoi(Achievement):
    def __init__(self):
        super().__init__(
            name="Quoi?", desc="Change your language settings", immutable=True
        )

    def user_progress(self, bot, user):
        return int(user.language != "english"), 1


beginning = Category(
    desc="Simple and basic achievements",
    challenges=[StartingOut(), Quoi()],
    icon=beginning_icon,
)
