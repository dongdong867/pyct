"""Conditions that record no fork, each reading a value pyct lost track of, and calls that
lose a tracked value without a word, for the sort-stuck-lines-by-cause story."""

_KEPT: list[int] = []


def counts(s: str) -> str:
    t = 0
    for c in s:
        if c == "z":
            t += 1
    if t > 25:
        return "many"
    return "few"


def counted(s: str) -> str:
    t = sum(1 for c in s if c == "z")
    if t > 25:
        return "many"
    return "few"


def ones(x: int) -> str:
    if bin(x).count("1") == 7:
        return "seven"
    return "other"


def zeros(x: int) -> str:
    y = bin(x)
    if y.count("0") == 3:
        return "three"
    return "other"


class Box:
    def __init__(self, x: int) -> None:
        self.size = bin(x).count("1")


def boxed(x: int) -> str:
    box = Box(x)
    if box.size == 7:
        return "seven"
    return "other"


def is_big(v: int) -> bool:
    if v > 100:
        return True
    return False


def judged(x: int) -> str:
    if is_big(x):
        return "big"
    return "small"


def packed(x: int) -> str:
    if bytes([x % 256, 1])[0] == 7:
        return "seven"
    return "other"


def keep(v: int) -> None:
    _KEPT.append(v)


def typed(x: int) -> str:
    keep(x)
    if isinstance(x, int):
        return "int"
    return "other"


def flipped(v: int) -> int:
    return v ^ 0


def lost_inside(x: int) -> int:
    return flipped(x)


def picked(x: int) -> str:
    if [10, 20, 30][x % 3] > 15:
        return "big"
    return "small"
