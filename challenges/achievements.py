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

        total = len(all_names) - 1

        names = set(all_names)

        tier = get_achievement_tier(user, total, names)

        display = f" `[{tier + 1}/{amt}]`"

        a = all_a[tier]

    else:
        total = 0
        all_names = [a.name]

    is_already_complete = user_has_complete(
        all_names, tier + 1 if display else 1, a.name, user
    )

    current_complete = await a.is_completed(ctx, user) or is_already_complete
    past_tier = display and tier + 1 > amt

    p1, p2 = await a.progress(ctx, user)

    if current_complete:
        p1 = max(p1, p2)

    bar = get_bar(p1 / p2, variant=int(bool(past_tier)))

    bar_display = f"{bar} `{p1}/{p2}`"

    emoji = icons.success if current_complete or past_tier else icons.danger

    return a, emoji, display, bar_display
