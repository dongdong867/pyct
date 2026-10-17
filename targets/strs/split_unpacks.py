"""Fixed-count unpacks of a split's list, which fork on the count before Python unpacks it."""


def parse(line: str):
    key, value = line.split("=", 1)
    if key == "port":
        return 1
    return 2


def two(s: str):
    a, b = s.split(",")
    if a == "x":
        return 1
    return 2


def starred(s: str):
    first, second, *rest = s.split(",")
    return first


def decided(s: str):
    parts = s.split(",")
    if len(parts) == 2:
        a, b = parts
        return a
    return ""


def into_a_list(s: str):
    [a, b] = s.split(",")
    return b


def five(n: int):
    a, b = 5
    return n


def one_item(n: int):
    a, b = [1]
    return n
