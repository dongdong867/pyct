"""Unpacks of values other than a split's list, which unpack as Python does with no new fork."""


def pair(n: int):
    return n, n + 1


def plain_tuple(n: int):
    a, b = (1, 2)
    t = (n, 3)
    c, d = t
    if c > 5:
        return a + d
    return b


def plain_list(n: int):
    items = [n, 4]
    a, b = items
    if a == 2:
        return b
    return 0


def generator(n: int):
    a, b = (x for x in (n, n * 2))
    if b > 10:
        return a
    return 0


def returned(n: int):
    a, b = pair(n)
    if b == 7:
        return a
    return 0


def tracked_list(xs: list[int]):
    a, b = xs
    if a > b:
        return 1
    return 0


def tracked_str(s: str):
    a, b = s
    if a == "q":
        return 1
    return 0


def swap(n: int, m: int):
    a, b = n, m
    a, b = b, a
    if a > b:
        return 1
    return 0


def split_in_a_loop(s: str):
    found = 0
    for a, b in (p.split("=") for p in s.split(";")):
        if a == b:
            found += 1
    return found


def tracked_dict(d: dict[str, int]):
    a, b = d
    if a == "k":
        return 1
    return 0
