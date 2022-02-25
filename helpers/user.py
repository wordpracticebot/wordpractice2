from static.themes import default


def generate_user_description(user):
    """Generate a description from user data"""
    # TODO: Finish generation of descriptions
    return "Nothing much is known about this user"


def get_user_cmds_run(bot, user) -> set:
    return bot.cmds_run.get(user.id, set()) | set(user.cmds_run)


def get_theme_display(clrs):
    for name, value in default.items():
        if value["colours"] == clrs:
            return name, value["icon"]
    return "", ""


def get_pacer_display(pacer: str):
    if pacer == "":
        return "None"

    if pacer == "avg":
        return "Average"

    if pacer == "rawavg":
        return "Raw Average"

    if pacer == "pb":
        return "Personal Best"

    return pacer + " wpm"


def get_pacer_type_name(pacer_type: int):
    if not pacer_type:
        return "Horizontal"

    return "Vertical"
