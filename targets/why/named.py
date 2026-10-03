FLAG = False


def false_flag(x: int) -> int:
    n = 0
    if x > 5:
        return 0
    if (x < 9) is FLAG:
        n += 1
    return n


def parenthesized_false(x: int) -> int:
    n = 0
    if x > 5:
        return 0
    if (x < 9) is (False):
        n += 1
    return n


def is_not_false_flag(x: int) -> int:
    n = 0
    if x > 5:
        return 0
    if (x > 9) is not FLAG:
        n += 1
    return n


def mixed_loop(x: int) -> int:
    n = 0
    if x > 5:
        return 0
    for v in (x < 9, True):
        if v is FLAG:
            n += 1
    return n


def chain_link(x: int, b: bool) -> int:
    if x > 5:
        return 0
    if x not in {10, 11} is b:
        return 1
    return 2
