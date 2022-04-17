from PIL import Image, ImageFont

from constants import FONT_SIZE

path = "./static/assets"

# Fonts
uni_sans_heavy = ImageFont.truetype(f"{path}/fonts/uni_sans_heavy_caps.ttf", 42)
arial = ImageFont.truetype(f"{path}/fonts/arial.ttf", FONT_SIZE)

# Images
achievement_base = Image.open(f"{path}/img/achievement_base.png")

beginning_icon = Image.open(f"{path}/img/beginning_icon.png")
speed_icon = Image.open(f"{path}/img/speed_icon.png")
badge_icon = Image.open(f"{path}/img/badge_icon.png")
endurance_icon = Image.open(f"{path}/img/endurance_icon.png")
