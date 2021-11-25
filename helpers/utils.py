# filter_commands function can only be accessed in help command
# https://github.com/Rapptz/discord.py/blob/master/discord/ext/commands/help.py
async def filter_commands(ctx, commands, sort=False, key=None):
    if sort and key is None:
        key = lambda c: c.name

    iterator = filter(lambda c: not c.hidden, commands)

    async def predicate(cmd):
        try:
            return await cmd.can_run(ctx)
        except commands.CommandError:
            return False

    ret = []
    for cmd in iterator:
        valid = await predicate(cmd)
        if valid:
            ret.append(cmd)

    if sort:
        ret.sort(key=key)

    return ret
