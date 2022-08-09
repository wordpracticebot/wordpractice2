import math
import time
from datetime import datetime

from data.constants import (
    AVG_AMT,
    MIN_PACER_SPEED,
    PACER_PLANES,
    UPDATE_24_HOUR_INTERVAL,
)
from static.themes import default


def get_user_cmds_run(bot, user) -> set:
    return bot.cmds_run.get(user.id, set()) | set(user.cmds_run)


def get_theme_display(clrs):
    for name, value in default.items():
        if value["colours"] == clrs:
            return name, value["icon"]

    return "Custom", ""


def get_pacer_name(pacer: str, wpm: int = None):
    if not pacer:
        return

    if pacer == "avg":
        name = "Average"

    elif pacer == "pb":
        name = "PB"

    else:
        return pacer + " wpm"

    if wpm is None:
        return name

    return f"{name} - {wpm} wpm"


def get_pacer_display(pacer_type, pacer_speed, wpm: int = None):
    pacer_type_name = PACER_PLANES[pacer_type].capitalize()

    pacer_name = get_pacer_name(pacer_speed, wpm)

    if pacer_name is not None:
        spacing = " " if wpm is None else "\n"

        pacer_name += f"{spacing}({pacer_type_name})"

    return pacer_name


def get_typing_average(user, amount: int = AVG_AMT):
    """
    user: user data
    amount: how many scores to get the statistics of
    """
    wpm = 0
    raw = 0
    acc = 0
    tw = 0
    cw = 0

    scores = user.scores[-amount:]

    for score in scores:
        wpm += score.wpm
        raw += score.raw
        acc += score.acc

        cw += score.cw
        tw += score.tw

    score_amt = min(len(user.scores), amount)

    if score_amt != 0:
        wpm = round(wpm / score_amt, 2)
        raw = round(raw / score_amt, 2)
        acc = round(acc / score_amt, 2)

    # wpm, raw wpm, accuracy, correct words, total words
    return wpm, raw, acc, cw, tw, scores


def get_daily_stat(stat: list[int]):
    from helpers.utils import get_start_of_day

    # Amount of minutes left in the day
    time_left = (
        24 * 60
        + (
            time.mktime(get_start_of_day().timetuple())
            - time.mktime(datetime.utcnow().timetuple())
        )
        / 60
    )

    start_index = int(time_left / UPDATE_24_HOUR_INTERVAL)

    return sum(stat[start_index:])


def get_expanded_24h_stat(stat: list[int], last_save: datetime):
    # Getting the amount of minutes since the last save
    passed = (datetime.utcnow() - last_save).total_seconds() / 60

    total_min = 60 * 24

    if passed >= total_min:
        return [0] * int(total_min / UPDATE_24_HOUR_INTERVAL)

    intervals = math.floor(passed / UPDATE_24_HOUR_INTERVAL)

    return stat[intervals:] + [0] * intervals


def get_pacer_speed(user, zone: str):
    if user.pacer_speed == "":
        return

    if user.pacer_speed == "avg":
        pacer = int(get_typing_average(user)[0])

    elif user.pacer_speed == "pb":
        if zone is None:
            return

        pacer = int(user.highspeed[zone].wpm)

    else:
        pacer = int(user.pacer_speed)

    if pacer < MIN_PACER_SPEED:
        return False

    return pacer
