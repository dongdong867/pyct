"""A target with one statement written over three lines."""


def total(x: int) -> int:
    y = max(x,
            10,
            -x)
    if y > 20:
        return y
    return 0
