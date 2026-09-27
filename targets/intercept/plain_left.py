RATE = 0.5


def floats(n: int) -> int:
    seen = 0
    if 0.5 + n > 3.0:
        seen += 1
    if 2.5 < n:
        seen += 2
    if 1.0 / n > 0.25:
        seen += 4
    if RATE * n > 3.0:
        seen += 8
    return seen


def bools(n: int) -> int:
    seen = 0
    if True + n > 5:
        seen += 1
    if True == n:
        seen += 2
    if True & (n > 0):
        seen += 4
    return seen
