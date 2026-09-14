# both sides of the second fork raise, so the input that raises is never the last one,
# whatever value cvc5 picks: the loop aims at the deepest open fork first, which is the
# one the raising input just hit
def guard(x: int) -> int:
    if x < 10:
        if x < 0:
            raise ValueError("negative")
        raise ValueError("small")
    return x
