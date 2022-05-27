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


async def check_all(ctx, user: dict):
    for iii, cv in enumerate(categories.values()):
        for ii, a in enumerate(cv.challenges):
            # Handling if it's not a tier
            if not isinstance(a, list):
                a = [a]

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


def get_achievement_tier(user, total: int, names: set):
    user_a = set(user.achievements)

    # getting the amount of achievements that the user has in that tier
    unique = names & user_a

    tier = sum([len(user.achievements[x]) for x in unique])

    return min(tier, total - 1)