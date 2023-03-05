import random
import textwrap
from io import BytesIO

import discord
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from data.constants import SIDE_BORDER, SPACING, STATIC_IMAGE_FORMAT, TOP_BORDER
from static.assets import achievement_base, arial, uni_sans_heavy

from .utils import run_in_executor


def _wrap_text(text, wrap_width):
    word_list = textwrap.wrap(text=text, width=wrap_width)

    joined = "\n".join(word_list)

    return word_list, joined


def get_width_height(word_list, wrap_width):
    largest_item = max(word_list, key=lambda x: arial.getsize(x)[0])

    width = (
        max(wrap_width * arial.getsize(" ")[0], arial.getsize(largest_item)[0])
        + SIDE_BORDER * 2
    )

    line_spacing = arial.getsize("A")[1] + SPACING

    height = int(TOP_BORDER * 2 + line_spacing * len(word_list))

    return (
        width,
        height,
    )


@run_in_executor()
def get_base(width: int, height: int, colours: list[str, str], fquote: list[str]):
    img = Image.new("RGB", (width, height), color=colours[0])
    d = ImageDraw.Draw(img)

    d.text(
        (SIDE_BORDER, TOP_BORDER), fquote, fill=colours[1], font=arial, spacing=SPACING
    )

    return img


@run_in_executor()
def get_highscore_captcha_img(base_img, text_colour):
    img = np.array(base_img)

    rows, cols, _ = img.shape

    width, height = base_img.size

    img_output = np.zeros(img.shape, dtype=img.dtype)

    get_random_coord = lambda: (
        random.randint(SIDE_BORDER, width),
        random.randint(TOP_BORDER, height),
    )

    for i in range(rows):
        for n in range(cols):
            x = int(2.8 * np.cos(2 * np.pi * i / 22.5))

            img_output[i, n] = img[i, (n + x) % cols]

    img = Image.fromarray(img_output)

    d = ImageDraw.Draw(img)

    for _ in range(4):
        d.line(
            (get_random_coord(), get_random_coord()),
            fill=text_colour,
            width=2,
        )
    return img


@run_in_executor()
def get_loading_img(img, text_colour):
    width, height = img.size

    blurred = img.filter(ImageFilter.GaussianBlur(radius=7))

    d = ImageDraw.Draw(blurred)

    msg = "Ready?"

    w, h = arial.getsize(msg)

    d.text(((width - w) / 2, (height - h) / 2), msg, fill=text_colour, font=arial)

    return blurred


async def get_raw_base_img(bot, raw_quote, wrap_width, theme):
    word_list, fquote = _wrap_text(raw_quote, wrap_width)

    width, height = get_width_height(word_list, wrap_width)

    return await get_base(bot, width, height, theme, fquote), word_list


async def get_base_img(bot, raw_quote, wrap_width, theme):
    return (await get_raw_base_img(bot, raw_quote, wrap_width, theme))[0]


def get_horizontal_pacer_rect(base, smooth, text_colour, i, y, _):
    im = base.copy()

    d = ImageDraw.Draw(im)

    d.rectangle(
        [
            SIDE_BORDER + i * smooth,
            y,
            SIDE_BORDER + arial.size / 3 + i * smooth,
            y + 2,
        ],
        fill=text_colour,
    )

    return im


def get_vertical_pacer_rect(base, smooth, text_colour, i, y, line_spacing):
    im = base.copy()

    d = ImageDraw.Draw(im)

    d.rectangle(
        [
            SIDE_BORDER + i * smooth,
            y - line_spacing * 0.8,
            SIDE_BORDER + 2 + i * smooth,
            y - 2,
        ],
        fill=text_colour,
    )

    return im


@run_in_executor()
def get_pacer(base, text_colour, quote, word_list, pacer, pacer_type):
    # Removes the dithering and reduces image size
    base = base.quantize(colors=3, method=Image.MAXCOVERAGE)

    # Scales the frame rate of the pacer so that slow pacers don't take forever to load
    smooth = round(-0.02 * pacer + 14, 2)

    images = []

    y = TOP_BORDER

    line_spacing = arial.getsize("A")[1] + SPACING

    rect_gen = get_horizontal_pacer_rect if pacer_type == 0 else get_vertical_pacer_rect

    for i, group in enumerate(word_list):
        y += line_spacing

        for i in range(1, int(arial.getsize(group)[0] // smooth)):
            im = rect_gen(base, smooth, text_colour, i, y, line_spacing)

            images.append(im)

    t = 12 * len(" ".join(quote)) / pacer - 0.25

    t = round((t / len(images) * 1000))

    buffer = BytesIO()

    images[0].save(
        buffer,
        format="gif",
        save_all=True,
        append_images=images[1:],
        duration=t,
        optimize=True,
        quality=10,
    )

    buffer.seek(0)

    return buffer


def save_discord_static_img(img, name, quantize=True, optimize=True):
    buffer = BytesIO()

    if quantize:
        # Decreases the image size a lot :)
        img = img.quantize(colors=6 if optimize else 30, method=Image.MAXCOVERAGE)

    img.save(buffer, STATIC_IMAGE_FORMAT, optimize=True)
    buffer.seek(0)

    return discord.File(buffer, filename=f"{name}.{STATIC_IMAGE_FORMAT}")


@run_in_executor()
def generate_achievement_image(name, icon):
    img = achievement_base.copy()

    if icon is not None:
        img_icon = icon.copy().resize((95, 95))
        img.paste(img_icon, (52, 52), img_icon)

    draw = ImageDraw.Draw(img)
    draw.text((240, 110), name, font=uni_sans_heavy)

    return save_discord_static_img(img, "achievement", quantize=False)
