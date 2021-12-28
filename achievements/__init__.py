from .beginning import beginning
from .speed import speed

categories = {
    "Beginning": beginning,
    "Speed": speed
    # "Endurance"
    # "Badges"
}

# TODO: cache results
async def check_all(user: dict):
    for cv in categories.values():
        for a in cv.challenges:
            if a.name in user.achievements or a.has_callback() is False:
                continue

            changer = await a.callback(user)

            # Checking if the achievement was completed
            if changer is False:
                continue

            yield a, changer
