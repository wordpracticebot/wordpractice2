from discord import SlashCommand, SlashCommandGroup

from bot import Context
from data.constants import DEFAULT_THEME
from helpers.user import get_user_cmds_run
from helpers.utils import get_command_name
from static.assets import beginning_icon

from .base import Achievement, Category
from .rewards import BadgeReward


class StartingOut(Achievement):
    def __init__(self):
        super().__init__(
            name="Starting out", desc="Use wordPractice for the first time"
        )

    async def progress(self, ctx: Context, user):
        return int(bool(user)), 1


class Quoi(Achievement):
    def __init__(self):
        super().__init__(name="Quoi?", desc="Change your language settings")

    async def progress(self, ctx: Context, user):
        return int(user.language != "english"), 1


class Competition(Achievement):
    def __init__(self):
        super().__init__(
            name="Competition",
            desc="Complete a race against another user",
        )

    async def progress(self, ctx: Context, user):
        return int(len(user.scores) > 0 and user.scores[-1].is_race), 1


class Colours(Achievement):
    def __init__(self):
        super().__init__(
            name="Colours!",
            desc="Change your typing test theme",
        )

    async def progress(self, ctx: Context, user):
        return int(bool(user.theme != DEFAULT_THEME)), 1


class OpenMinded(Achievement):
    def __init__(self):
        super().__init__(name="Open-minded", desc="Run every single __slash command__")

    async def progress(self, ctx: Context, user):
        slash_cmds = filter(
            lambda c: isinstance(c, SlashCommand)
            and not isinstance(c, SlashCommandGroup)
            and not getattr(c.cog, "hidden", False),
            ctx.bot.walk_application_commands(),
        )

        all_cmds = [get_command_name(cmd) for cmd in slash_cmds]

        return len(set(all_cmds) & set(get_user_cmds_run(ctx.bot, user))), len(all_cmds)


beginning = Category(
    desc="Simple and basic achievements",
    challenges=[StartingOut(), Quoi(), Colours(), Competition(), OpenMinded()],
    icon=beginning_icon,
    reward=BadgeReward("gold_plant"),
)
