import random

random.seed(7)


def draw(x: int) -> str:
    # the first draw after the import's seed, the same in every input that starts fresh
    if x > random.randrange(100):
        return "above"
    return "at most"
