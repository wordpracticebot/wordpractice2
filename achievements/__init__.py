from constants import BAR_SIZE
from icons import progress_bar

from .badges import badges
from .beginning import beginning
from .endurance import endurance
from .speed import speed

categories = {
    "Beginning": beginning,
    "Speed": speed,
    "Badges": badges,
    "Endurance": endurance,
}


def handle_achievement(user, a, tier):
    if tier <= len(user.achievements.get(a.name, [])) or a.has_callback() is False:
        return None

    changer = a.callback(user)

    # Checking if the achievement was not completed
    if changer is False:
        return None

    return a, changer


def check_all(user: dict):
    for iii, cv in enumerate(categories.values()):
        for ii, a in enumerate(cv.challenges):
            # Handling if it's not a tier
            is_tier = True
            if not isinstance(a, list):
                a = [a]
                is_tier = False

            for i, n in enumerate(a):
                result = handle_achievement(user, n, i + 1)

                if result is None:
                    continue

                yield result, i if is_tier else None, (iii, ii)


def get_bar(progress):
    """Creates a progress bar out of emojis from progress float"""
    p = int(progress * BAR_SIZE)
    bar = ""
    for i in range(BAR_SIZE):
        if i == 0:
            bar += progress_bar[0][int(p != 0)]
        elif i == BAR_SIZE - 1:
            bar += progress_bar[2][int(p >= BAR_SIZE)]
        else:
            bar += progress_bar[1][2 if i == p else int(i > p)]
    return bar


def get_achievement_tier(user, names):
    user_a = set(user.achievements)

    if user_a.isdisjoint(names):
        tier = 0
    else:
        # getting the amount of achievements that the user has in that tier
        tier = sorted([len(user.achievements[x]) for x in set(names) & user_a])[-1]

    return tier
