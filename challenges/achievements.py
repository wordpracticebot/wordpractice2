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


def user_has_complete(all_names, i, name, user):
    a_count = all_names[: i + 1].count(name)

    return a_count <= len(user.achievements.get(name, []))


async def check_achievements(ctx, user: dict):
    for iii, cv in enumerate(categories.values()):
        for ii, c in enumerate(cv.challenges):
            a = sum(c, []) if isinstance(c, list) else [c]

            all_names = [b.name for b in a]

            for i, n in enumerate(a):

                # checking if the user has already completed the achievement
                if user_has_complete(all_names, i, n.name, user):
                    continue

                if (
                    await n.is_completed(ctx, user)
                    or n.name in ctx.achievements_completed
                ):
                    # achievement object, count of achievement, identifer
                    yield n, i if all_names.count(n.name) > 1 else None, cv, (iii, ii)

                continue


def is_a_done(a, user):
    if isinstance(a, list):
        all_a = sum(a, [])

        all_names = [m.name for m in all_a]

        tier = get_achievement_tier(user, len(all_names), set(all_names))

        total = len(a[0])

        return tier + 1 >= total, tier, total, all_a[tier]

    else:
        is_done = a.name in user.achievements

        return is_done, None, 1, a


def is_category_complete(c, user):
    for a in c.challenges:
        is_done, *_ = is_a_done(a, user)

        if is_done is False:
            return False

    return True


def check_categories(user: dict, user_old: dict):
    for n, c in categories.items():

        if is_category_complete(c, user) and is_category_complete(c, user_old) is False:
            yield n, c

        continue


def get_achievement_tier(user, total: int, names: set):
    user_a = set(user.achievements)

    # getting the amount of achievements that the user has in that tier
    unique = names & user_a

    tier = sum([len(user.achievements[x]) for x in unique])

    return min(tier, total - 1)


async def get_achievement_display(ctx, user, e):
    is_done, tier, total, a = is_a_done(e, user)

    if tier is not None:
        display = f" `[{tier + 1}/{total}]`"
        variant = int(tier > total)
    else:
        display = ""
        variant = 0

    p1, p2 = await a.progress(ctx, user)

    if await a.is_completed(ctx, user):
        p1 = max(p1, p2)

    bar = get_bar(p1 / p2, variant=variant)

    bar_display = f"{bar} `{p1}/{p2}`"

    emoji = icons.success if is_done else icons.danger

    return a, emoji, display, bar_display
