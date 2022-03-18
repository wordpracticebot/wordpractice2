from textwrap import TextWrapper

from PIL import Image, ImageDraw, ImageFilter

from constants import FONT_SIZE, SIDE_BORDER, SPACING, TOP_BORDER, WRAP_WIDTH
from static.assets import arial

WRAPPER = TextWrapper(width=WRAP_WIDTH)


def get_width_height(word_list):
    largest_item = max(word_list, key=lambda x: arial.getsize(x)[0])

    width = arial.getsize(largest_item)[0] + SIDE_BORDER * 2

    line_spacing = arial.getsize("A")[1] + SPACING

    height = int(TOP_BORDER * 2 + line_spacing * len(word_list))

    return (
        width,
        height,
    )


def wrap_text(text):
    word_list = WRAPPER.wrap(text=text)

    joined = "\n".join(word_list)

    return word_list, joined


def get_base(width, height, colours, fquote):
    img = Image.new("RGB", (width, height), color=colours[0])
    d = ImageDraw.Draw(img)

    d.text(
        (SIDE_BORDER, TOP_BORDER), fquote, fill=colours[1], font=arial, spacing=SPACING
    )

    return img


def get_loading_img(img, text_colour):
    width, height = img.size

    blurred = img.filter(ImageFilter.GaussianBlur(radius=6))

    # Creating the image mask
    mask = Image.new("L", img.size)

    d = ImageDraw.Draw(mask)

    d.rectangle([0, 0, width, height], fill=255)

    img2 = Image.composite(blurred, img, mask)

    d = ImageDraw.Draw(img2)

    msg = "Ready?"

    w, h = arial.getsize(msg)

    d.text(((width - w) / 2, (height - h) / 2), msg, fill=text_colour, font=arial)

    return img2
