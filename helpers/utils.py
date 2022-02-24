import random
from discord import SlashCommand


def format_slash_command(command: SlashCommand):
    return (f"{command.parent.name} " if command.parent else "") + command.name


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

        values.pop(items.index(c))

    return chosen
