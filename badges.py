"""
The badge system has a unique identifier for each badge. 
Only the identifier is stored in the user document
"""

badges = {}


def get_badge_from_id(badge_id):
    return badges.get(badge_id)
