import calendar
import difflib
import functools
import math
import random
from datetime import datetime, timezone
from typing import Callable

from discord import SlashCommand, SlashCommandGroup
from discord.ext import commands

from constants import SUPPORT_SERVER_INVITE, TEST_ZONES
from helpers.ui import create_link_view
from helpers.user import get_user_cmds_run
from icons import h_progress_bar, overflow_bar, v_progress_bar
from static.hints import date_hints, hints, random_hints

BARS = (h_progress_bar, overflow_bar, v_progress_bar)


def get_command_name(command):
    if isinstance(command, SlashCommand):
        return (f"{command.parent.name} " if command.parent else "") + command.name

    return command.qualified_name


def format_command(command):
    if isinstance(command, SlashCommand):
        return get_command_name(command)

    return f"{command} {command.signature}"


def filter_commands(ctx, cmds):
    if ctx.is_slash:
        types = (SlashCommand, SlashCommandGroup)
    else:
        types = (commands.Command, commands.Group)

    filter_cmds = (
        lambda c: isinstance(c, types)
        and not getattr(c.cog, "hidden", False)
        and not getattr(c, "hidden", False)
    )

    all_cmds = filter(filter_cmds, cmds)

    return list(all_cmds)


def cmd_run_before(ctx, user):
    return get_command_name(ctx.command) in get_user_cmds_run(ctx.bot, user)


def weighted_lottery(seed, values, picks):
    """
    picks weighted values from a list of lists without duplicates
    """
    gen = random.Random()
    gen.seed(seed)

    chosen = []

    for _ in range(picks):
        items, weights = zip(*values)

        c = gen.choices(items, weights=weights, k=1)[0]

        chosen.append(c)

        # Removing values of the same type
        values = list(filter(lambda x: not isinstance(x[0], type(c)), values))

    return chosen


def get_start_of_day():
    today = datetime.utcnow()

    return datetime(
        year=today.year,
        month=today.month,
        day=today.day,
        hour=0,
        minute=0,
        second=0,
        tzinfo=timezone.utc,
    )


def get_test_input_stats(u_input: list, quote: list):
    """
    Evaluates test from input and quote
    """

    # Ignoring word case
    quote = [q.lower() for q in quote]
    u_input = [u.lower() for u in u_input]

    # User input shift
    u_shift = 0

    # Quote word index on line
    w_shift = 0

    # Stats
    cw = 0  # correct words
    cc = 0  # correct characters
    word_history = []

    # Extra characters from missed words or characters
    extra_cc = 0

    u = 0

    def _eval_one_iteration(shift=0):
        mu_index = u_index + shift
        mw_index = w_index + shift

        # The the word is fully correct
        if u_input[mu_index] == quote[mw_index]:
            return 0

        # If the word is not fully correct

        # Checking if it isn't the last word inputted
        if mu_index + 1 < len(u_input):
            # Space was added inside a word
            if u_input[mu_index] + u_input[mu_index + 1] == quote[mw_index]:
                return 1

            # Extra word was added
            if u_input[mu_index + 1] == quote[mw_index]:
                return 2

            if mw_index + 1 < len(quote):
                # Space was added at wrong point between two words
                if (
                    u_input[mu_index] + u_input[mu_index + 1]
                    == quote[mw_index] + quote[mw_index + 1]
                ):
                    return 3

        # Checking if it isn't the last word in the quote
        if mw_index + 1 < len(quote):
            # Space was missed between two words
            if u_input[mu_index] == quote[mw_index] + quote[mw_index + 1]:
                return 4

        return

    while (u_index := u_shift + u) < len(u_input) and (w_index := w_shift + u) < len(
        quote
    ):

        if u_index < len(u_input) and u_index != 0:
            # For the space after the word
            cc += 1

        u += 1

        result = _eval_one_iteration()

        if result is not None:
            if result == 0:
                word_history.append(u_input[u_index])

                cc += len(quote[w_index])
                cw += 1

            elif result == 1:
                word_history.append(f"__{quote[w_index]}__")
                cc += len(quote[w_index]) - 1
                u_shift += 1

            elif result == 2:
                word_history.append(f"~~{u_input[u_index]}~~")
                w_shift -= 1

            elif result == 3:
                combined = u_input[u_index] + " " + u_input[u_index + 1]

                word_history.append(f"__{combined}__")

                cc += len(combined) - 1

                w_shift += 1
                u_shift += 1

            elif result == 4:
                word_history.append(f"{quote[w_index]} __  __ {quote[w_index + 1]}")
                cc += len(u_input[u_index])
                w_shift += 1
                extra_cc += 1

            continue

        # Checking if it isn't the last word in the quote
        if w_index + 1 < len(quote):
            # One or more words were skipped
            if u_input[u_index] in (search := quote[w_index:]):
                is_skipped = True

                if u_index + 1 < len(u_input):
                    # If next word is correct then it is most likely that the word was mistyped as another ones
                    result = _eval_one_iteration(1)

                    if result is not None:
                        is_skipped = False

                if is_skipped:
                    skip_index = search.index(u_input[u_index])

                    w_shift += skip_index - 1
                    u_shift -= 1

                    for w in search[:skip_index]:
                        # Punishing for skipping words
                        extra_cc += 1

                        word_history.append(f"__{w}__")

                    # Removes the space that is added at the top of sthe loop
                    cc -= 1

                    continue

        # calculating number of differences between the quote and input word
        wc = sum(
            map(
                lambda x: x[0] != " ",
                difflib.ndiff(u_input[u_index], quote[w_index]),
            )
        )

        longest = max(len(u_input[u_index]), len(quote[w_index]))

        cc += max(longest - wc, 0)

        word_history.append(f"~~{u_input[u_index]}~~ **({quote[w_index]})**")

        if (extra := len(quote[w_index]) - len(u_input[u_index])) > 0:
            extra_cc += extra

    return cc, word_history, extra_cc, cw


def datetime_to_unix(date):
    return calendar.timegm(date.utctimetuple())


def is_today(d):
    today = datetime.utcnow().date()

    return d.date() == today


# Calculates consistency from scores
# Formula by Kogasa: https://github.com/Miodec/monkeytype
def calculate_consistency(nums: list) -> float:
    length = len(nums)
    mean = sum(nums) / length

    x = math.sqrt(sum([(x - mean) ** 2 for x in nums]))
    y = x / mean

    return round(100 * (1 - math.tanh(y + y**3 / 3 + y**5 / 5)), 2)
    # lol


def calculate_score_consistency(scores):
    if len(scores) == 0:
        return 0

    return calculate_consistency([s.wpm + s.raw + s.acc for s in scores])


def get_test_stats(u_input, quote, end_time):
    cc, rws, extra_cc, cw = get_test_input_stats(u_input, quote)

    # total characters
    tc = len(" ".join(u_input))

    extra_tc = tc + extra_cc

    acc = 0 if extra_tc == 0 else round(cc / extra_tc * 100, 2)
    wpm = round(cc / (end_time / 12), 2)
    raw = round(tc / (end_time / 12), 2)

    # Limiting the word history to 1024 characters (embed field value limit)
    adjusted_history = [
        rws[i]
        for i in range(len(rws))
        if [sum(list(map(len, rws))[: j + 1]) for j in range(len(rws))][i] + 1 <= 825
    ]

    word_history = " ".join(adjusted_history)

    if len(adjusted_history) < len(rws):
        word_history += "..."

    return wpm, raw, acc, cc, cw, word_history


def get_bar(progress: float, *, size: int = 10, variant: int = 0, split: bool = False):
    """Creates a progress bar out of emojis"""
    bar_list = BARS[variant]

    p = progress * size

    bar = []

    for i in range(size):
        level = 0 if int(r := p - i) > 0 else 2 if r >= 0.5 else 1

        if i == 0:
            bar.append(bar_list[0][level])
        elif i == size - 1:
            bar.append(bar_list[2][level])

        else:
            if 1.5 > r >= 1:
                level = 3

            bar.append(bar_list[1][level])

    if split is False:
        return ("\n" if variant > 1 else "").join(bar)

    return bar


def get_xp_earned(cc: int) -> int:
    return round(1 + (cc * 2))


def get_test_type(test_type_int: int, length: int):
    zone = next(
        (f"{t.capitalize()} " for t, v in TEST_ZONES.items() if length in v), ""
    )

    # fmt: off
    return zone + (
        "Quote"
        if test_type_int == 0

        else "Dictionary"
        if test_type_int == 1

        else "Practice"
        if test_type_int == 2
        
        else None
        )
    # fmt: on


def get_test_zone(cw: int):
    for n, r in TEST_ZONES.items():
        if cw in r:
            return n, r

    return None


def get_test_zone_name(cw: int):
    m = get_test_zone(cw)

    if m is None:
        return

    n, r = m

    return n, f"({r[0]}-{r[-1]}) words"


# https://stackoverflow.com/a/64506715
def run_in_executor(_func):
    @functools.wraps(_func)
    def wrapped(bot, *args, **kwargs):
        func = functools.partial(_func, *args, **kwargs)
        return bot.loop.run_in_executor(executor=None, func=func)

    return wrapped


async def message_banned_user(ctx, user, reason):
    embed = ctx.error_embed(
        title="You were banned",
        description=(
            f"Reason: {reason}\n\n"
            "Join the support server and create a ticket to request a ban appeal"
        ),
    )

    view = create_link_view({"Support Server": SUPPORT_SERVER_INVITE})

    try:
        await user.send(embed=embed, view=view)
    except Exception:
        pass


def copy_doc(copy_func: Callable) -> Callable:
    def wrapper(func: Callable) -> Callable:
        func.__doc__ = copy_func.description or copy_func.help
        return func

    return wrapper


async def invoke_slash_command(cmd, cog, ctx, *args):
    kwargs = {n._parameter_name: arg for n, arg in zip(cmd.options, args)}

    await cmd.callback(cog, ctx, **kwargs)


def get_hint():
    # 1 in 100 chance of an alternative footer
    if random.randint(0, 100) == 0:
        p = []

        # Date based footers
        now = datetime.utcnow()

        for d, h in zip(date_hints):
            if [now.month, now.day] == d:
                p += h

        # VERY RARE
        if random.randint(0, 25) == 0:
            p += random_hints

        if p != []:
            return random.choice(p)

    return "Hint: " + random.choice(hints)
