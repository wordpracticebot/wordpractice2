import random

import discord

from static.hints import hints


class CustomEmbed(discord.Embed):
    def __init__(self, bot, add_footer=True, **kwargs):
        if add_footer:
            self._footer = {}

            hint = self.get_random_hint()

            self._footer["text"] = f"Hint: {hint}"
            if bot.user.avatar:
                self._footer["icon_url"] = bot.user.avatar.url

        super().__init__(**kwargs)

    def get_random_hint(self):
        return random.choice(hints)


class BaseView(discord.ui.View):
    def __init__(self, personal=True):
        super().__init__()

        self.personal = personal

    async def interaction_check(self, interaction):
        if self.personal or (
            interaction.user and interaction.user.id == self.ctx.author.id
        ):
            return True

        await interaction.response.send_message(
            "You are not the author of this command", ephemeral=True
        )
        return False

    async def on_error(self, error, item, interaction):
        if interaction.response.is_done():
            await interaction.followup.send("An unknown error happened", ephemeral=True)
        else:
            await interaction.response.send_message(
                "An unknown error happened", ephemeral=True
            )

        # TODO: remove this in production + log error
        raise error


class PageView(BaseView):
    def __init__(self, ctx):
        self.ctx = ctx

        super().__init__()

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        await self.response.edit_original_message(view=self)

    async def create_page(self):
        return self.ctx.embed()

    async def update_buttons(self):
        ...

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


class ScrollView(PageView):
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


class DictButton(discord.ui.Button):
    def toggle_success(self):
        self.style = discord.ButtonStyle.success

    def toggle_regular(self):
        self.style = discord.ButtonStyle.primary

    async def callback(self, interaction):
        self.toggle_success()

        await self.view.update_all(interaction, self.label)


class ViewFromDict(PageView):
    def __init__(self, ctx, the_dict):
        super().__init__(ctx)

        self.the_dict = the_dict

    @property
    def order(self):
        return list(self.the_dict.keys())

    @property
    def button(self):
        return DictButton

    async def update_message(self, interaction):
        embed = await self.create_page()
        await interaction.message.edit(embed=embed, view=self)

    async def create_page(self):
        ...

    async def update_buttons(self, page):
        if self.page is not None:
            prev_index = self.order.index(self.page)

            self.children[prev_index].toggle_regular()

        self.page = page

    async def update_all(self, interaction, page):
        await self.update_buttons(page)
        await self.update_message(interaction)

    async def start(self):
        start_index = 0
        # Generating the buttons
        for i, name in enumerate(self.order):
            button = self.button(label=name)

            if i == start_index:
                self.page = name
                button.toggle_success()

            self.add_item(button)

        embed = await self.create_page()
        self.response = await self.ctx.respond(embed=embed, view=self)


def create_link_view(links: dict[str, str]):
    """
    links: {NAME: URL}
    """
    view = discord.ui.View()

    for name, url in links.items():
        view.add_item(discord.ui.Button(label=name, url=url))

    return view
