import icons
from helpers.utils import get_bar

from .badges import badges
from .beginning import beginning
from .endurance import endurance
from .typing import typing

categories = {
    "Beginning": beginning,
    "Typing": typing,
    "Badges": badges,
    "Endurance": endurance,
}


async def check_achievements(ctx, user: dict):
    for iii, cv in enumerate(categories.values()):
        for ii, c in enumerate(cv.challenges):
            a = sum(c, []) if isinstance(c, list) else [c]

            all_names = [b.name for b in a]

            for i, n in enumerate(a):
                a_count = all_names[: i + 1].count(n.name)

                # checking if the user has already completed the achievement
                if a_count <= len(user.achievements.get(n.name, [])):
                    continue

                if (
                    await n.is_completed(ctx, user)
                    or n.name in ctx.achievements_completed
                ):
                    # achievement object, count of achievement, identifer
                    yield n, i if all_names.count(n.name) > 1 else None, cv, (iii, ii)

                continue


def check_categories(user: dict):
    for n, c in categories.items():

        if c.is_done(user):
            yield n, c

        continue


def get_achievement_tier(user, total: int, names: set):
    user_a = set(user.achievements)

    # getting the amount of achievements that the user has in that tier
    unique = names & user_a

    tier = sum([len(user.achievements[x]) for x in unique])

    return min(tier, total - 1)


async def get_achievement_display(ctx, user, a):
    display = ""

    # Tiers
    if isinstance(a, list):
        all_a = sum(a, [])

        amt = len(a[0])

        all_names = [m.name for m in all_a]
        names = set(all_names)

        tier = get_achievement_tier(user, len(all_names), names)

        display = f" `[{tier + 1}/{amt}]`"

        a = all_a[tier]

    p = await a.progress(ctx, user)

    # fmt: off
    is_completed = (
        await a.is_completed(ctx, user)
        or (display and tier + 1 > amt)
    )
    # fmt: on

    bar = get_bar(p[0] / p[1], variant=int(bool(is_completed and display)))

    bar_display = f"{bar} `{p[0]}/{p[1]}`"

    emoji = icons.success if is_completed else icons.danger

    return a, emoji, display, bar_display
