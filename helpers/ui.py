import asyncio
import math
import time
from typing import TYPE_CHECKING, Callable, Coroutine, Iterable, Union

import discord
from discord.utils import escape_markdown

import data.icons as icons
from data.constants import DEFAULT_VIEW_TIMEOUT, SUPPORT_SERVER_INVITE
from helpers.errors import OnGoingTest

if TYPE_CHECKING:
    from bot import Context


def create_link_view(links: dict[str, str]):
    """
    links: {NAME: URL}
    """
    view = discord.ui.View()

    for name, url in links.items():
        view.add_item(discord.ui.Button(label=name, url=url))

    return view


def get_log_embed(ctx: "Context", title, additional: str, error=False, author=None):
    if author is None:
        author = ctx.author

    name = escape_markdown(str(author))
    guild = escape_markdown(str(ctx.guild))

    timestamp = int(time.time())

    embed_gen = ctx.error_embed if error else ctx.default_embed

    embed = embed_gen(
        title=title,
        description=(
            f"**User:** {name}\n"
            f"**User ID:** {author.id}\n"
            f"**Server:** {guild} ({None if ctx.guild is None else ctx.guild.id})\n"
            f"{additional}\n"
            f"**Timestamp:** <t:{timestamp}:R>"
        ),
    )

    return embed


class CustomEmbed(discord.Embed):
    def __init__(self, bot, hint=None, add_footer=True, **kwargs):
        if add_footer:
            self._footer = {}

            self._footer["text"] = hint
            if bot.user.display_avatar:
                self._footer["icon_url"] = bot.user.display_avatar.url

        super().__init__(**kwargs)


class BaseView(discord.ui.View):
    def __init__(
        self,
        ctx: "Context",
        timeout=DEFAULT_VIEW_TIMEOUT,
        personal=True,
    ):
        super().__init__(timeout=timeout)

        self.ctx = ctx
        self.personal = personal

    async def on_timeout(self):
        if self._message:
            # Not disabling any link buttons
            exclusions = [
                c
                for c in self.children
                if isinstance(c, discord.ui.Button) and c.url is not None
            ]

            self.disable_all_items(exclusions=exclusions)

            await self._message.edit(view=self)

    async def interaction_check(self, interaction):
        if self.personal is False or (
            interaction.user and interaction.user.id == self.ctx.author.id
        ):
            if self.ctx.initial_user is not None and self.ctx.initial_user.banned:
                await interaction.response.send_message(
                    "You are banned!", ephemeral=True
                )
                return False

            return True

        await interaction.response.send_message(
            "You are not the author of this command!", ephemeral=True
        )
        return False

    async def on_error(self, error, _, inter):
        if inter.response.is_done():
            send = inter.followup.send
        else:
            send = inter.response.send_message

        if isinstance(error, OnGoingTest):
            return await self.ctx.bot.handle_ongoing_test_error(send)

        self.ctx.bot.active_end(self.ctx.author.id)

        view = create_link_view({"Support Server": SUPPORT_SERVER_INVITE})

        embed = self.ctx.error_embed(
            title=f"{icons.danger} `ERROR!` An Unexpected Error Occured!",
            description="> Please report this through our support server so we can fix it.",
        )

        try:
            await send(embed=embed, view=view, ephemeral=True)
        except Exception:
            pass

        embed = get_log_embed(
            self.ctx,
            title="Unexpected Error (in view)",
            additional=f"**Done:** {inter.response.is_done()}",
            error=True,
        )

        await self.ctx.bot.log_the_error(embed, error)


class PageView(BaseView):
    def __init__(self, ctx: "Context"):
        self.ctx = ctx

        self.loading_msg = None

        super().__init__(ctx)

    async def create_page(self) -> discord.Embed:
        ...

    async def update_buttons(self):
        ...

    async def update_message(self, interaction):
        embed = await self.create_page()

        view = self

        items = None

        if isinstance(embed, tuple):
            embed, items = embed

            for item in items:
                view.add_item(item)

        try:
            await interaction.response.edit_message(embed=embed, view=view)
        except discord.InteractionResponded:
            await interaction.edit_original_message(embed=embed, view=view)

        if items is not None:
            for item in items:
                view.remove_item(item)

    async def update_all(self, interaction):
        await self.update_buttons()

        await self.wait_for(self.update_message(interaction), interaction)

    async def defer_interaction(self, interaction=None):
        await asyncio.sleep(0.3)

        if interaction.response.is_done() is False:
            try:
                await interaction.response.defer()
            except (discord.InteractionResponded, discord.NotFound):
                pass

            content = f"**Loading {icons.loading}**"

            if self.loading_msg is None:
                self.loading_msg = await self.ctx.respond(content, ephemeral=True)
            else:
                self.loading_msg = await self.loading_msg.edit(content)

    async def wait_for(self, callback: Coroutine, interaction):
        await asyncio.gather(self.defer_interaction(interaction), callback)

        if interaction.response.is_done() and self.loading_msg is not None:
            self.loading_msg = await self.loading_msg.edit("**Done Loading**")

    async def start(self):
        embed = await self.create_page()
        await self.update_buttons()

        await self.ctx.respond(embed=embed, view=self)


class ScrollView(PageView):
    def __init__(
        self,
        ctx: "Context",
        *,
        iter: Union[Iterable, Callable],
        per_page: int = 1,
        row=0,
    ):
        super().__init__(ctx)

        self._iter = iter

        self.per_page = per_page

        self.row = row

        self.page = 0

        self.add_items()

    @property
    def iter(self):
        if isinstance(self._iter, Callable):
            return self._iter()

        return self._iter

    @property
    def total(self):
        return len(self.iter)

    @property
    def max_page(self) -> int:
        return math.ceil(self.total / self.per_page) or 1

    @property
    def compact(self):
        return self.max_page <= 7

    @property
    def has_btns(self):
        return self.max_page > 1

    @property
    def start_page(self):
        return self.page * self.per_page

    @property
    def end_page(self):
        return (self.page + 1) * self.per_page

    @property
    def items(self):
        return self.iter[self.start_page : self.end_page]

    def add_scroll_btn(self, emoji, callback):
        btn = discord.ui.Button(
            emoji=discord.PartialEmoji.from_str(emoji),
            style=discord.ButtonStyle.grey,
            row=self.row,
        )
        btn.callback = callback

        self.add_item(btn)

        setattr(self, callback.__name__, btn)

        return btn

    def add_items(self):
        if not self.has_btns:
            return

        if self.compact is False:
            self.add_scroll_btn(icons.fast_left_arrow, self.scroll_to_front)

        self.add_scroll_btn(icons.left_arrow, self.scroll_forward)

        self.add_scroll_btn(icons.right_arrow, self.scroll_backward)

        if self.compact is False:
            self.add_scroll_btn(icons.fast_right_arrow, self.scroll_to_back)

    async def update_buttons(self):
        if not self.has_btns:
            return

        first_page = self.page == 0
        last_page = self.page == self.max_page - 1

        self.scroll_forward.disabled = first_page
        self.scroll_backward.disabled = last_page

        if self.compact:
            return

        self.scroll_to_front.disabled = first_page
        self.scroll_to_back.disabled = last_page

    async def scroll_to_front(self, interaction):
        if self.page != 0:
            self.page = 0
            await self.update_all(interaction)

    async def scroll_forward(self, interaction):
        if self.page != 0:
            self.page -= 1
            await self.update_all(interaction)

    async def scroll_backward(self, interaction):
        if self.page != self.max_page:
            self.page += 1
            await self.update_all(interaction)

    async def scroll_to_back(self, interaction):
        if self.page != self.max_page:
            self.page = self.max_page - 1

            await self.update_all(interaction)


class DictButton(discord.ui.Button):
    success = discord.ButtonStyle.success
    regular = discord.ButtonStyle.primary

    @property
    def is_display_success(self):
        return self.style == self.success

    def toggle_success(self):
        self.style = self.success

    def toggle_regular(self):
        self.style = self.regular

    def toggle_eligible(self, value):
        ...

    async def callback(self, interaction):
        if self.is_display_success is False:
            self.toggle_success()

            await self.view.update_all(interaction, self.label)


class ViewFromDict(PageView):
    def __init__(self, ctx: "Context", the_dict, row=0):
        super().__init__(ctx)

        self.the_dict = the_dict
        self.row = row

    @property
    def order(self):
        return list(self.the_dict.keys())

    @property
    def button(self):
        return DictButton

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
            btn = self.button(label=name, row=self.row + i // 5)

            if i == start_index:
                self.page = name
                btn.toggle_success()

            else:
                btn.toggle_regular()

            btn.toggle_eligible(self.the_dict[self.order[i]])

            self.add_item(btn)

        embed = await self.create_page()
        await self.ctx.respond(embed=embed, view=self)
