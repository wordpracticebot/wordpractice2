import random

import discord


class CustomEmbed(discord.Embed):
    def __init__(self, bot, add_footer=True, **kwargs):
        if add_footer:
            self._footer = {}

            hint = self.get_random_hint()

            self._footer["text"] = f"Hint: {hint}"
            self._footer["icon_url"] = str(bot.user.avatar_url)

        super().__init__(**kwargs)

    # TODO: add proper hints
    def get_random_hint(self):
        return random.choice(["yes", "no", "maybe"])
