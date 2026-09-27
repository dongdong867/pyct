import random


def pick(n: int) -> str:
    chosen = random.Random(0).sample(range(n), 1)
    if chosen[0] > 7:
        return "high"
    return "low"
