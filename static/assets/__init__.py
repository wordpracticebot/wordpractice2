from PIL import Image, ImageFont

from constants import FONT_SIZE

path = "./static/assets"

# Fonts
uni_sans_heavy = ImageFont.truetype(f"{path}/fonts/uni_sans_heavy_caps.ttf", 42)
arial = ImageFont.truetype(f"{path}/fonts/arial.ttf", FONT_SIZE)

# Images
achievement_base = Image.open(f"{path}/img/achievement_base.png")
