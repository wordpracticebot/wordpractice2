"""
Challenges are not directly related to achievements but they use almost the same mechamism
"""
import random
from functools import lru_cache

from constants import CHALLENGE_AMT
from helpers.user import get_daily_stat
from helpers.utils import datetime_to_unix, get_start_of_day, is_today, weighted_lottery

from .base import Challenge, get_in_row
from .rewards import XPReward


class WordChallenge(Challenge):
    def __init__(self, word_amt):

        super().__init__(desc=f"Type {word_amt} words")

        self.word_amt = word_amt

    async def user_progress(self, ctx, user):
        return get_daily_stat(user.last24[0]), self.word_amt


class VoteChallenge(Challenge):
    def __init__(self):
        super().__init__(desc="Vote for wordPractice")

    async def user_progress(self, ctx, user):
        votes_today = any(is_today(v) for v in user.last_voted.values())

        return int(votes_today), 1


class AccuracyChallenge(Challenge):
    def __init__(self, amt):
        super().__init__(
            desc=f"Complete {amt} tests in a row with 100% accuracy", immutable=True
        )

        self.amt = amt

    async def user_progress(self, ctx, user):
        return (
            get_in_row(user.scores, lambda s: s.acc == 100 and is_today(s.timestamp)),
            self.amt,
        )


class QuoteChallenge(Challenge):
    def __init__(self, amt):
        super().__init__(desc=f"Completed {amt} quote typing tests", immutable=True)

        self.amt = amt

    async def user_progress(self, ctx, user):
        return int(len(user.scores) == 0 or not user.scores[-1].test_type_int == 0), 1


@lru_cache(maxsize=1)
def _get_challenges_from_unix(start_unix):
    challenges = weighted_lottery(start_unix, CHALLENGES, CHALLENGE_AMT)

    gen = random.Random()
    gen.seed(start_unix)

    reward = XPReward(gen.randint(15, 35) * 100)

    return challenges, reward


def get_daily_challenges():
    start = get_start_of_day()

    # Getting the unix time of the start of the day
    start_unix = datetime_to_unix(start)

    return _get_challenges_from_unix(start_unix)


CHALLENGES = [
    [VoteChallenge(), 5],
    [WordChallenge(750), 2],
    [WordChallenge(1000), 3],
    [WordChallenge(1250), 3],
    [WordChallenge(1500), 2],
    [AccuracyChallenge(3), 1],
    [AccuracyChallenge(5), 2],
    [AccuracyChallenge(8), 2],
    [AccuracyChallenge(10), 1],
    [QuoteChallenge(2), 1],
    [QuoteChallenge(4), 1],
]
