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


def get_typing_average(user, amount: int):
    """
    user: user data
    amount: how many scores to get the statistics of
    """
    wpm = 0
    raw = 0
    acc = 0
    tw = 0
    cw = 0

    scores = user.scores[:amount]

    for score in scores:
        wpm += score.wpm
        raw += score.raw

        cw += score.cw
        tw += score.tw

    score_amt = min(len(user.scores), amount)

    if score_amt != 0:
        wpm = round(wpm / score_amt, 2)
        raw = round(raw / score_amt, 2)
        acc = round(acc / score_amt, 2)

    # wpm, raw wpm, accuracy, correct words, total words
    return wpm, raw, acc, cw, tw, scores
