def not_in(s: str) -> int:
    if s == "":
        return 0
    if not s in "":
        if len(s) < 0:
            return 1
        return 2
    return 3


def while_not_in(s: str) -> int:
    if s == "":
        return 0
    while not s in "":
        return 1
    return 2


def is_not_true(x: int) -> int:
    if x > 9:
        return 0
    if (x > 9) is not True:
        return 1
    return 2
