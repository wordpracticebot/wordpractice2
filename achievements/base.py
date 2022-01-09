"""
callback -> 

True = finished but no state change
False = not finished
Callable[[dict], dict] = state change
"""

"""
Challenges:
[[a,b,c], a, b] 
"""


class Achievement:
    def __init__(self, name: str, desc: str, reward: str = None):
        self.name = name
        self.desc = desc
        self.reward = reward

    def progress(self, user) -> int:
        return int(self.name in user.achievements), 1

    def has_callback(self):
        return callable(getattr(self.__class__, "callback", False))


class Category:
    def __init__(self, desc: str, challenges: list):
        self.desc = desc
        self.challenges = challenges
