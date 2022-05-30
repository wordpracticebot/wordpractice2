from discord.commands import SlashCommand

from helpers.user import get_user_cmds_run
from helpers.utils import format_slash_command
from static.assets import beginning_icon

from .base import Achievement, Category


class StartingOut(Achievement):
    def __init__(self):
        super().__init__(
            name="Starting out", desc="Use wordPractice for the first time"
        )

    async def user_progress(self, ctx, user):
        return int(bool(user)), 1


class Quoi(Achievement):
    def __init__(self):
        super().__init__(
            name="Quoi?", desc="Change your language settings", immutable=True
        )

    async def user_progress(self, ctx, user):
        return int(user.language != "english"), 1


class Competition(Achievement):
    def __init__(self):
        super().__init__(
            name="Competition",
            desc="Complete a race against another user",
            immutable=True,
        )

    async def user_progress(self, ctx, user):
        return int(len(user.scores) == 0 or not user.scores[-1].is_race), 1


class OpenMinded(Achievement):
    def __init__(self):
        super().__init__(name="Open-minded", desc="Run every single command")

    async def user_progress(self, ctx, user):
        slash_cmds = filter(
            lambda c: isinstance(c, SlashCommand)
            and not getattr(c.cog, "hidden", False),
            ctx.bot.walk_application_commands(),
        )

        all_cmds = [format_slash_command(cmd) for cmd in slash_cmds]

        return len(set(all_cmds) & set(get_user_cmds_run(ctx.bot, user))), len(all_cmds)


beginning = Category(
    desc="Simple and basic achievements",
    challenges=[StartingOut(), Quoi(), Competition(), OpenMinded()],
    icon=beginning_icon,
)
