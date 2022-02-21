"""
The badge system has a unique identifier for each badge. 
Only the identifier is stored in the user document
"""

# fmt: off

default = {
    "grey": "",
    "orange": "",
    "lightblue": "",
    "purple": "",
    "red": "",
    "blue": "",
    "soldtogaming": "",
    "blackfridaytag": "",
    "tree": "",
    "card": "",
    "redribbon": "",
    "flag": "",
    "diamond": "",
    "spiderweb": "",
    "witchhat": "",
    "first": "",
    "candybucket": "",
    "pumpkin": "",
    "snowflake": "",
    "snowman": "",
    "mittens": "",
    "firework": "",
    "hat": "",
    "heart": "",
    "chocolate": "",
    "soldtogamingevent": "",
    "present": "",
    "sapling": "",
    "clover": "",
    "cloud": "",
    "easterbasket": "",
    "suitcase": "",
    "glasses": "",
    "compass": "",
    "candycorn": "",
    "bat": "",
    "mapleleaf": "",
    "twig": "",
    "contestaward": "",
    "jesterhat": "",
    "whopeecushion": "",
    "sandbucket": "",
    "flower": "",
    "mug": "",
    "popsicle": "",
    "camera": "",
    "turkey": "",
    "coal": "",
    "snowmobile": "",
    "heart": "",
    "surfboard": "",
    "umbrella": "",
    "watermelon": "",
    "hat": "",
    "goldpot": "",
    "wateringcan": "",
    "sunscreen": "",
    "beachball": "",
    "kayak": "",
    "chocoloate": "",
    "cup": "",
    "lifesaver": "",
    "apple": "",
    "backpack": "",
    "ruler": "",
    "rainboot": "",
    "acorn": "",
    "campfire": "",
    "stocking": "",
    "ornament": "",
}
# fmt: on


def get_badge_from_id(badge_id: str):
    return default.get(badge_id)


def get_badges_from_ids(badge_ids: list):
    return [b for badge in badge_ids if (b := default.get(badge)) is not None]
