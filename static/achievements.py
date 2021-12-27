from datetime import datetime

"""
Structure of an achievement

"NAME": {
    "description": str,
    ?"callback": function(user) -> bool # handles checking if the achievement is completed and giving the reward
    ?"progress": function(user) -> int # handles chekcing the progress of the achievement
    ?"reward" str 
}
"""

beginning = {
    "description": "",
    "challenges": {
        "Starting out": {
            "description": "Use wordPractice for the first time",
            "callback": lambda user: bool(user),
        },
        "Support!": {"description": "Invite wordPractice to a server that you own"},
    },
}
categories = {
    "Beginning": beginning
    # "Endurance"
    # "Speed"
    # "Badges"
}

# TODO: cache results
async def check_all(ctx, user: dict):
    for cv in categories.values():
        for name, value in cv["challenges"].items():
            if name in user["achievements"] or "callback" not in "achievements":
                continue

            is_complete = value["callback"](user)

            if is_complete:
                # Updating achievement in database
                await ctx.bot.mongo.add_achievement(ctx.author, name)

            # TODO: send achievement image

            yield name
