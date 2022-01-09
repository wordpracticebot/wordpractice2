from constants import BAR_SIZE, PROGRESS

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


def handle_achievement(a, user):
    if a.name in user.achievements or a.has_callback() is False:
        return None

    changer = a.callback(user)

    # Checking if the achievement was completed
    if changer is False:
        return None

    return a, changer


def check_all(user: dict):
    for cv in categories.values():
        for a in cv.challenges:
            # Handling if it's not a tier
            if not isinstance(a, list):
                a = [a]

            for n in a:
                result = handle_achievement(n, user)

                if result is None:
                    continue

                yield result


def get_bar(progress):
    """Creates a progress bar out of emojis from progress float"""
    p = int(progress * BAR_SIZE)
    bar = ""
    for i in range(BAR_SIZE):
        if i == 0:
            bar += PROGRESS[0][int(p != 0)]
        elif i == BAR_SIZE - 1:
            bar += PROGRESS[2][int(p >= BAR_SIZE)]
        else:
            bar += PROGRESS[1][2 if i == p else int(i > p)]
    return bar


def get_achievement_tier(user, names):
    user_a = set(user.achievements)

    # if the last or 2nd last is completed, the user must be on the last
    if names[-1] in user_a or names[-2] in user_a:
        tier = len(names) - 1
    if user_a.isdisjoint(names):
        tier = 0
    else:
        # getting the highest achievement in tier that user has
        tier = sorted([names.index(x) for x in set(names) & user_a])[-1] + 1

    return tier
