import calendar
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


def get_test_input_stats(u_input, quote):
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
    cc = 0  # correct characters
    word_history = []

    # Extra characters from missed words or characters
    extra_cc = 0

    u = 0

    while not (
        (w_index := w_shift + u) >= len(quote)
        or (u_index := u_shift + u) > len(u_input)
    ):
        u += 1

        not_last_input = u_index + 1 < len(u_input)

        # The the word is fully correct
        if u_input[u_index] == quote[w_index]:
            word_history.append(u_input[u_index])

            cc += len(quote[w_index]) + int(not_last_input)

        # If the word is not fully correct
        else:
            # Checking if it isn't the last word inputted
            if not_last_input:
                # For the space after the word
                cc += 1

                # Space was added inside a word
                if u_input[u_index] + u_input[u_index + 1] == quote[w_index]:
                    word_history.append(f"__{quote[w_index]}__")
                    cc += len(quote[w_index]) - 1
                    u_shift += 1
                    continue

                # Extra word was added
                if u_input[u_index + 1] == quote[w_index]:
                    word_history.append(f"~~{u_input[u_index]}~~")
                    w_shift -= 1
                    continue

            # Checking if it isn't the last word in the quote
            if w_index + 1 < len(quote):
                # Space was missed between two words
                if u_input[u_index] == quote[w_index] + quote[w_index + 1]:
                    word_history.append(f"{quote[w_index]} __  __ {quote[w_index + 1]}")
                    cc += len(u_input[u_index])
                    w_shift += 1
                    extra_cc += 1
                    continue

                # One or more words were skipped
                if u_input[u_index] in (search := quote[w_index:]):
                    skip_index = search.index(u_input[u_index])

                    w_shift += skip_index - 1
                    u_shift -= 1

                    for w in search[:skip_index]:
                        # Punishing for skipping words
                        extra_cc += 1

                        word_history.append(f"__{w}__")

                    # Removes the space that is added at the top of the loop
                    cc -= 1

                    continue

            # A word is mistyped
            cc += sum(int(c == w) for c, w in zip(u_input[u_index], quote[w_index]))

            word_history.append(f"~~{u_input[u_index]}~~ **({quote[w_index]})**")

            if (extra := len(quote[w_index]) - len(u_input[u_index])) > 0:
                extra_cc += extra

    return cc, word_history, extra_cc


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
