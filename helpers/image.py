import random
import textwrap

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from constants import SIDE_BORDER, SPACING, TOP_BORDER
from static.assets import arial


def quantize_img(img):
    return img.quantize(method=Image.NONE)

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


def wrap_text(text, wrap_width):
    word_list = textwrap.wrap(text=text, width=wrap_width)

    joined = "\n".join(word_list)

    return word_list, joined


def get_base(width, height, colours, fquote):
    img = Image.new("RGB", (width, height), color=colours[0])
    d = ImageDraw.Draw(img)

    d.text(
        (SIDE_BORDER, TOP_BORDER), fquote, fill=colours[1], font=arial, spacing=SPACING
    )

    return img


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
            x = int(2.75 * np.cos(2 * np.pi * i / 22.9))

            img_output[i, n] = img[i, (n + x) % cols]

    img = Image.fromarray(img_output)

    d = ImageDraw.Draw(img)

    for _ in range(3):
        d.line(
            (get_random_coord(), get_random_coord()),
            fill=text_colour,
            width=2,
        )
    return img


def get_loading_img(img, text_colour):
    width, height = img.size

    blurred = img.filter(ImageFilter.GaussianBlur(radius=6))

    d = ImageDraw.Draw(blurred)

    msg = "Ready?"

    w, h = arial.getsize(msg)

    d.text(((width - w) / 2, (height - h) / 2), msg, fill=text_colour, font=arial)

    return blurred
