"""A sweep fixture: the module whose file holds total."""


def total(n: int) -> int:
    if n > 10:
        return n - 1
    return n
