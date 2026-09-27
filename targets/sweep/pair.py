"""A sweep fixture: two functions that run and cover different lines, and one with nothing to
vary."""


def first(n: int) -> str:
    if n > 3:
        return "big"
    return "small"


def second(n: int) -> str:
    if n == 7:
        return "seven"
    return "other"


def third() -> str:
    return "none"
