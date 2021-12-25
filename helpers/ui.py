import random

import discord


def create_link_view(links: dict[str, str]):
    """
    links: {NAME: URL}
    """
    view = discord.ui.View()

    for name, url in links.items():
        view.add_item(discord.ui.Button(label=name, url=url))

    return view


class CustomEmbed(discord.Embed):
    def __init__(self, bot, add_footer=True, **kwargs):
        if add_footer:
            self._footer = {}

            hint = self.get_random_hint()

            self._footer["text"] = f"Hint: {hint}"
            if bot.user.avatar:
                self._footer["icon_url"] = bot.user.avatar.url

        super().__init__(**kwargs)

    # TODO: add proper hints
    def get_random_hint(self):
        return random.choice(["yes", "no", "maybe"])


class BaseView(discord.ui.View):
    def __init__(self, ctx):
        self.ctx = ctx

        super().__init__()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        await self.response.edit_original_message(view=self)

    async def interaction_check(self, interaction):
        if self.ctx.author.id != interaction.user.id:
            await interaction.response.send_message(
                "You are not the author of this command.", ephemeral=True
            )
            return False
        return True

    async def interaction_check(self, interaction):
        if interaction.user and interaction.user.id == self.ctx.author.id:
            return True
        await interaction.response.send_message(
            "You are not the author of this command", ephemeral=True
        )
        return False

    async def create_page(self):
        return self.ctx.bot.embed()

    async def update_buttons(self):
        pass

    async def on_error(self, error, item, interaction):
        if interaction.response.is_done():
            await interaction.followup.send("An unknown error happened", ephemeral=True)
        else:
            await interaction.response.send_message(
                "An unknown error happened", ephemeral=True
            )

        # TODO: remove this in production + log error
        raise error

    async def update_message(self, interaction):
        embed = await self.create_page()
        await interaction.message.edit(embed=embed, view=self)

    async def update_all(self, interaction):
        await self.update_buttons()
        await self.update_message(interaction)

    async def start(self):
        embed = await self.create_page()
        await self.update_buttons()
        self.response = await self.ctx.respond(embed=embed, view=self)


class ScrollView(BaseView):
    def __init__(self, ctx, max_page: int, compact=True):
        super().__init__(ctx)

        self.compact = compact
        self.max_page = max_page
        self.page = 0

        self.remove_proper_items()

    def remove_proper_items(self):
        if self.compact:
            self.remove_item(self.scroll_to_front)
            self.remove_item(self.scroll_to_back)

    async def update_buttons(self):
        first_page = self.page == 0
        last_page = self.page == self.max_page - 1

        self.scroll_forward.disabled = first_page
        self.scroll_backward.disabled = last_page

        if self.compact:
            return

        self.scroll_to_front.disabled = first_page
        self.scroll_to_back.disabled = last_page

    @discord.ui.button(emoji="⏪", style=discord.ButtonStyle.grey)
    async def scroll_to_front(self, button, interaction):
        if self.page != 0:
            self.page = 0
            await self.update_all(interaction)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.grey)
    async def scroll_forward(self, button, interaction):
        if self.page != 0:
            self.page -= 1
            await self.update_all(interaction)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.grey)
    async def scroll_backward(self, button, interaction):
        if self.page != self.max_page:
            self.page += 1
            await self.update_all(interaction)

    @discord.ui.button(emoji="⏩", style=discord.ButtonStyle.grey)
    async def scroll_to_back(self, button, interaction):
        button.disabled = True
        if self.page != self.max_page:
            self.page = self.max_page - 1

            await self.update_all(interaction)


def create_link_view(links: dict):
    """
    Creates a link view
    links: {name: url}
    """

    view = discord.ui.View()

    for label, url in links.items():
        item = discord.ui.Button(style=discord.ButtonStyle.link, label=label, url=url)
        view.add_item(item=item)

    return view
