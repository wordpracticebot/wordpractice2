from .speed import speed
from .beginning import beginning

categories = {
    "Beginning": beginning,
    "Speed": speed
    # "Endurance"
    # "Badges"
}

# TODO: cache results
async def check_all(ctx, user: dict):
    for cv in categories.values():
        for a in cv.challenges:
            if a.name in user.achievements or a.has_callback() is False:
                continue

            query = await a.callback(user)

            # Checking if the achievement was completed by seeing if a query was returned
            if not query:
                continue

            yield a.name, query if a.reward else None
