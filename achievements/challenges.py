"""
Challenges are not directly related to achievements but they use almost the same mechamism
"""
import random
from datetime import datetime
from functools import lru_cache

from constants import CHALLENGE_AMT
from helpers.user import get_daily_stat
from helpers.utils import datetime_to_unix, get_start_of_day, weighted_lottery

from .base import Challenge, XPReward, get_in_row


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
        return (
            int(
                any(
                    v.date() == datetime.utcnow().date()
                    for v in user.last_voted.values()
                )
            ),
            1,
        )


class AccuracyChallenge(Challenge):
    def __init__(self, amt):
        super().__init__(
            desc=f"Complete {amt} tests in a row with 100% accuracy", immutable=True
        )

        self.amt = amt

    async def user_progress(self, ctx, user):
        return get_in_row(user.scores, lambda s: s.acc == 100), self.amt


# TODO: add more challenges and proper weights
CHALLENGES = [
    [VoteChallenge(), 5],
    [WordChallenge(750), 1],
    [WordChallenge(1000), 2],
    [WordChallenge(1250), 2],
    [WordChallenge(1500), 1],
    [AccuracyChallenge(3), 1],
    [AccuracyChallenge(5), 2],
    [AccuracyChallenge(8), 2],
    [AccuracyChallenge(10), 1],
]


@lru_cache(maxsize=1)
def get_challenges_from_unix(start_unix):
    challenges = weighted_lottery(start_unix, CHALLENGES, CHALLENGE_AMT)

    # Getting the xp reward
    gen = random.Random()
    gen.seed(start_unix)

    reward = XPReward(gen.randint(15, 35) * 100)

    return challenges, reward


def get_daily_challenges():
    start = get_start_of_day()

    # Getting the unix time of the start of the day
    start_unix = datetime_to_unix(start)

    return get_challenges_from_unix(start_unix)
