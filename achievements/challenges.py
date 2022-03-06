"""
Challenges are not directly related to achievements but they use almost the same mechamism
"""
import random
import time
from datetime import datetime
from functools import lru_cache

from constants import CHALLENGE_AMT
from helpers.utils import get_start_of_day, weighted_lottery


class Challenge:
    def __init__(self, title, description):
        self.title = title
        self.description = description


class WordChallenge(Challenge):
    def __init__(self, word_amt):

        super().__init__(
            f"Type {word_amt} words", "Complete typing tests add to your word count"
        )

        self.word_amt = word_amt

    def progress(self, user) -> tuple:
        return sum(user.last24[0]), self.word_amt


class VoteChallenge(Challenge):
    def __init__(self):
        super().__init__("Vote for wordPractice", "Type /vote for more information")

    def progress(self, user) -> tuple:
        return (
            int(
                any(
                    v.date() == datetime.utcnow().date()
                    for v in user.last_voted.values()
                )
            ),
            1,
        )


# TODO: add more challenges and proper weights
CHALLENGES = [
    [VoteChallenge(), 2],
    [WordChallenge(750), 2],
    [WordChallenge(1000), 2],
    [WordChallenge(1250), 2],
    [WordChallenge(1500), 2],
]


@lru_cache(maxsize=1)
def get_challenges_from_unix(start_unix):
    challenges = weighted_lottery(start_unix, CHALLENGES, CHALLENGE_AMT)

    # Getting the xp reward
    gen = random.Random()
    gen.seed(start_unix)

    xp = gen.randint(15, 35) * 100

    return challenges, xp


def get_daily_challenges():
    start = get_start_of_day()

    # Getting the unix time of the start of the day
    start_unix = time.mktime(start.timetuple())

    return get_challenges_from_unix(start_unix)
