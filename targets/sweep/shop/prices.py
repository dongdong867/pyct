"""A sweep fixture: the module whose file holds total."""


def total(n: int) -> int:
    if n > 10:
        return n - 1
    return n


def discount(n: int) -> int:
    if n < 0:
        return 0
    return n
