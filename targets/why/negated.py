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


L = [10, 11]
FLAG = True


def not_in_set(x: int) -> int:
    if x > 5:
        return 0
    if not x in {10, 11}:
        return 1
    return 2


def not_in_set_written(x: int) -> int:
    if x > 5:
        return 0
    if x not in {10, 11}:
        return 1
    return 2


def not_in_list(x: int) -> int:
    if x > 5:
        return 0
    if not x in L:
        return 1
    return 2


def plain_is_false(x: int) -> int:
    done = None
    if done is False:
        return 1
    return 2


def is_not_flag(x: int) -> int:
    if x > 9:
        return 0
    if (x > 9) is not FLAG:
        return 1
    return 2
