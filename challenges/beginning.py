from helpers.user import get_user_cmds_run
from helpers.utils import get_slash_cmd_names
from static.assets import beginning_icon

from .base import Achievement, Category


class StartingOut(Achievement):
    def __init__(self):
        super().__init__(
            name="Starting out", desc="Use wordPractice for the first time"
        )

    async def progress(self, ctx, user):
        return int(bool(user)), 1


class Quoi(Achievement):
    def __init__(self):
        super().__init__(name="Quoi?", desc="Change your language settings")

    async def progress(self, ctx, user):
        return int(user.language != "english"), 1


class Competition(Achievement):
    def __init__(self):
        super().__init__(
            name="Competition",
            desc="Complete a race against another user",
        )

    async def progress(self, ctx, user):
        return int(len(user.scores) > 0 and user.scores[-1].is_race), 1


class OpenMinded(Achievement):
    def __init__(self):
        super().__init__(name="Open-minded", desc="Run every single command")

    async def progress(self, ctx, user):
        all_cmds = get_slash_cmd_names(ctx.bot)

        return len(set(all_cmds) & set(get_user_cmds_run(ctx.bot, user))), len(all_cmds)


beginning = Category(
    desc="Simple and basic achievements",
    challenges=[StartingOut(), Quoi(), Competition(), OpenMinded()],
    icon=beginning_icon,
)
