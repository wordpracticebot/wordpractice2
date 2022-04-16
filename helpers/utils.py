import calendar
import difflib
import math
import random
from datetime import datetime, timezone

from discord import SlashCommand

from helpers.user import get_user_cmds_run


def format_slash_command(command: SlashCommand):
    return (f"{command.parent.name} " if command.parent else "") + command.name


def cmd_run_before(ctx, user):
    return format_slash_command(ctx.command) in get_user_cmds_run(ctx.bot, user)


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

        return None

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
                combined = u_input[u_index] + u_input[u_index + 1]
                word_history.append(f"__{combined}__")
                cc += len(combined)
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


# Calculates consistency from scores
# Formula by Kogasa: https://github.com/Miodec/monkeytype
def calculate_consistency(nums: list) -> float:
    length = len(nums)
    mean = sum(nums) / length

    x = math.sqrt(sum([(x - mean) ** 2 for x in nums]))
    y = x / mean

    return round(100 * (1 - math.tanh(y + y ** 3 / 3 + y ** 5 / 5)), 2)
    # lol


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
