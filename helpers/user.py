def generate_user_description(user):
    """Generate a description from user data"""
    # TODO: Finish generation of descriptions
    return f"Nothing much is known about {user.min_name}"


def get_user_cmds_run(bot, user) -> set:
    return bot.cmds_run.get(user.id, set()) | set(user.cmds_run)
