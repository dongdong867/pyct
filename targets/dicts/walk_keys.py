"""Walks whose key the solver may choose: a small dict's own walk, and the walks that keep
today's keys."""


def int_below(d: dict[int, int]):
    for k in d:
        if d[k] < 5:
            if 1 not in d:
                return 1
    return 0


def ab_only(d: dict[str, int]):
    for k in d:
        if d[k] > 5 and "ab" not in d:
            return 1
    return 0


def first_of_two(d: dict[str, int]):
    if len(d) > 1:
        for k in d:
            if d[k] > 5 and "ab" not in d:
                return 1
            return 0
    return 2


def named(d: dict[str, int]):
    for k in d:
        if k == "admin":
            return 1
    return 0


def stored_first(d: dict[str, int]):
    d["zz"] = 0
    for k in d:
        if d[k] > 5 and "a" not in d:
            return 1
    return 0


def marked_first(n: str, d: dict[str, int]):
    d[n] = 0
    for k in d:
        pass
    for k in d:
        if d[k] > 5 and "a" not in d:
            return 1
    return 0


def sorted_walk(d: dict[str, int]):
    for k in sorted(d):
        if d[k] > 5 and "a" not in d:
            return 1
    return 0


def listed_walk(d: dict[str, int]):
    for k in list(d):
        if d[k] > 5 and "a" not in d:
            return 1
    return 0


def reversed_walk(d: dict[str, int]):
    for k in reversed(d):
        if d[k] > 5 and "a" not in d:
            return 1
    return 0


def first_key(d: dict[str, int]):
    if d:
        k = next(iter(d))
        if d[k] > 5 and "a" not in d:
            return 1
    return 0


def copied_walk(d: dict[str, int]):
    copied = dict(d)
    for k in copied:
        if copied[k] > 5 and "a" not in d:
            return 1
    return 0


def counted(d: dict[str, int]):
    n = 0
    for k in d:
        n += 1
    if n > 1 and "ab" not in d:
        return 1
    return 0


def twice(d: dict[str, int]):
    for k in d:
        break
    for k in d:
        if d[k] > 5 and "ab" not in d:
            return 1
    return 0


def looked_up(n: int, d: dict[int, int]):
    if n in d:
        if d[n] > 5:
            return 1
    return 0


def grown(d: dict[str, int]):
    for k in d:
        if d[k] > 5:
            d[k + "x"] = 0
    return 0
