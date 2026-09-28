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


TABLE = {"a": 1}


def not_first_in(s: str) -> int:
    if s == "":
        return 0
    if not s[0] in "":
        return 1
    return 2


def int_not_in(s: str) -> int:
    if not s.isdigit():
        return 0
    if len(s) > 5:
        return 0
    if int(s) not in {100000, 200000}:
        return 1
    return 2


def is_false_no_else(x: int) -> int:
    n = 0
    if x > 5:
        return 0
    if (x < 9) is False:
        n += 1
    return n


def while_is_not_true(x: int) -> int:
    n = 0
    if x > 5:
        return 0
    while (x < 9) is not True:
        n += 1
    return n


def not_in_table(x: int) -> int:
    key = "zz"
    if not key in TABLE:
        return 1
    return 2


def false_is_compare(x: int) -> int:
    n = 0
    if x > 5:
        return 0
    if False is (x < 9):
        n += 1
    return n


def pair_one(x: int, flag: bool) -> int:
    if x > 5:
        return 0
    if not flag:
        return 5
    v = x > 9
    n = False
    if v is flag:
        return n
    return 2


def ifexp_is_false(x: int) -> int:
    n = 0
    if x > 5:
        return 0
    if (x < 9 if x > 0 else x < 8) is False:
        n += 1
    return n


def false_is_ifexp(x: int) -> int:
    n = 0
    if x > 5:
        return 0
    if False is (x < 9 if x > 0 else x < 8):
        n += 1
    return n
