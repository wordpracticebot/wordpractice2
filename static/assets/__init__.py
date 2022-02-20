from PIL import Image, ImageFont

path = "./static/assets"

# Fonts
uni_sans_heavy = ImageFont.truetype(f"{path}/fonts/uni_sans_heavy_caps.ttf", 42)

# Images
achievement_base = Image.open(f"{path}/img/achievement_base.png")
