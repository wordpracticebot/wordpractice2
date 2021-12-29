from .badges import badges
from .beginning import beginning
from .speed import speed

categories = {
    "Beginning": beginning,
    "Speed": speed,
    "Badges": badges,
    # "Endurance"
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
