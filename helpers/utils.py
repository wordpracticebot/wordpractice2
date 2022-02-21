from discord import SlashCommand


def format_slash_command(command: SlashCommand):
    return (f"{command.parent.name} " if command.parent else "") + command.name
