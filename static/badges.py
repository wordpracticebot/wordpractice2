"""
The badge system has a unique identifier for each badge. 
Only the identifier is stored in the user document
"""

# fmt: off

default = {
    "grey": "<:grey:965483700223631420>",
    "orange": "<:orange:965483700374630400>",
    "lightblue": "<:lightblue:965483700462682183>",
    "purple": "<:purple:965483700395581461>",
    "red": "<:red:965483700378828810>",
    "blue": "<:blue:965483700206845963>",
    "soldtogaming": "<:soldtogaming:965631000531050506>",
    "blackfridaytag": "<:blackfridaytag:965630999855792158>",
    "tree": "<:tree:965631000082255912>",
    "card": "<:card:965630999788679208>",
    "redribbon": "<:redribbon:965631000191324160>",
    "flag": "<:flag:965630999981596702>",
    "diamond": "<:diamond:965631000187125820>",
    "spiderweb": "<:spiderweb:965630999755124757>",
    "witchhat": "<:witchhat:965631000178753556>",
    "first": "<:first:965631000166154280>",
    "candybucket": "<:candybucket:965630999885144144>",
    "pumpkin": "<:pumpkin:965630999969030275>",
    "snowflake": "<:snowflake:965632028949237810>",
    "snowman": "<:snowman:965633064757772350>",
    "mittens": "<:mittens:965633064921350264>",
    "firework": "<:firework:965633064824877166>",
    "hat": "<:hat:965638260615422002>",
    "heart": "<:heart:965638260560912384>",
    "chocolate": "<:chocolate:965638260544118865>",
    "present": "<:present:965638260653162516>",
    "sapling": "<:sapling:965638260703526952>",
    "clover": "<:clover:965638260766437376>",
    "cloud": "<:cloud:965638260229537864>",
    "easterbasket": "<:easterbasket:965638260732878928>",
    "suitcase": "<:suitcase:965638260355383326>",
    "sunglasses": "<:sunglasses:965638260422479932>",
    "candycorn": "<:candycorn:965638260015640696>",
    "bat": "<:bat:965638260019855380>",
    "mapleleaf": "<:mapleleaf:965638260481228822>",
    "twig": "<:twig:965638260288286792>",
    "contestaward": "<:contestaward:965638259810111509>",
    "jesterhat": "<:jesterhat:965638260774797342>",
    "whopeecushion": "<:whopeecushion:965638260674166844>",
    "sandbucket": "<:sandbucket:965638260279902228>",
    "tulip": "<:tulip:965638260795793588>",
    "mug": "<:mug:965638260707704892>",
    "popsicle": "<:popsicle:965638260745461881>",
    "camera": "<:camera:965638259776573461>",
    "turkey": "<:turkey:965638260766425128>",
    "coal": "<:coal:965650550408499270>",
    "snowmobile": "<:snowmobile:965650550337187920>",
    "surfboard": "<:surfboard:965650550286864384>",
    "umbrella": "<:umbrella:965650549993259079>",
    "watermelon": "<:watermelon:965650550437838989>",
    "goldpot": "<:goldpot:965651030404632656>",
    "wateringcan": "<:wateringcan:965651030421426277>",
    "sunscreen": "<:sunscreen:965651030719221900>",
    "beachball": "<:beachball:965651030824087662>",
    "kayak": "<:kayak:965651030635319366>",
    "lifesaver": "<:lifesaver:965651030673084466>",
    "apple": "<:apple:965651397741797386>",
    "backpack": "<:backpack:965651397859237898>",
    "ruler": "<:ruler:965651030845050961>",
    "rainboot": "<:rainboot:965651030719234129>",
    "acorn": "<:acorn:965651434932695120>",
    "campfire": "<:campfire:965651030215905280>",
    "stocking": "<:stocking:965651030694060042>",
    "ornament": "<:ornament:965651030459154452>",
    "shovel": "<:shovel:965651030593404969>",
    "rainbow": "<:rainbow:965651030819893308>",
    "gold_keyboard": "<:gold_keyboard:986006270068817920>",
    "gold_plant": "<:gold_plant:986006269020233749>",
    "gold_badge": "<:gold_badge:986006271348064256>",
    "thomas": "<:thomas:986006272472141865>",
    "pineapple": "<:pineapple:992984425224749097>",
    "sun": "<:sun:992987841992863815>",
    "fan": "<:fan:1004396761634316368>",
    "icecube": "<:icecube:1004396760426365019>",
    "icecream": "<:icecream:1004396759033856114>",
    "rake": "<:rake:1015625201838460988>",
    "mushroom": "<:mushroom:1015625199745499186>"
}
# fmt: on


def get_badge_from_id(badge_id: str):
    return default.get(badge_id)


def get_badges_from_ids(badge_ids: list):
    return [default.get(badge) for badge in badge_ids]
