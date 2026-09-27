def above(x: int) -> str:
    if abs(x) > 3:
        return "far"
    return "near"


def calls(x: int) -> int:
    n = 0
    if -abs(x) < -3:
        n += 1
    if abs(x) ** 2 > 9:
        n += 1
    if abs(x - 1) > 3:
        n += 1
    if abs(abs(x) - 5) > 1:
        n += 1
    return n


def negations(x: int) -> int:
    n = 0
    if -x < 3:
        n += 1
    if -(x + 1) > 0:
        n += 1
    if -(-x) > 1:
        n += 1
    return n
