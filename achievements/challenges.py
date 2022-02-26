"""
Challenges are not directly related to achievements but they use almost the same mechamism
"""
import time
from datetime import datetime
from functools import lru_cache

from constants import CHALLENGE_AMT
from helpers.utils import weighted_lottery


class WordChallenge:
    def __init__(self, word_amt):
        self.word_amt = word_amt

    def progress(self, user) -> tuple:
        return sum(user.last24[0]), self.word_amt


class VoteChallenge:
    def progress(self, user) -> tuple:
        return user.last_voted.date() == datetime.utcnow().date()


# TODO: add actual challenges
CHALLENGES = [
    [VoteChallenge(), 2],
    [WordChallenge(100), 2],
    [WordChallenge(200), 2],
    [WordChallenge(500), 1],
]


@lru_cache(maxsize=1)
def get_daily_challenges():
    today = datetime.utcnow()
    start = datetime(
        year=today.year, month=today.month, day=today.day, hour=0, second=0
    )

    # Getting the unix time of the start of the day
    start_unix = time.mktime(start.timetuple())

    return weighted_lottery(start_unix, CHALLENGES, CHALLENGE_AMT)
