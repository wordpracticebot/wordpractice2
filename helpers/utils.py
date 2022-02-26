import random

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

        yield c

    return chosen
