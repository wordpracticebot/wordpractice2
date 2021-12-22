from discord.ext import commands


class ImproperArgument(commands.BadArgument):
    """
    Subclass of BadArgument that contains possible options
    
    BadArgument should be used instead of no options are needed
    """
    def __init__(self, options: list):
        self.options = options
