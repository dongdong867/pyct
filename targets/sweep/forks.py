"""A sweep fixture: one function that forks on its argument."""


def sign(n: int) -> int:
    if n > 0:
        return 1
    return 0
