def walk_twice(s: str):
    n = 0
    for c in s:
        n += 1
    for c in s:
        if c == "#":
            return -1
    return n


def concat_walk(s: str):
    for c in s + "!":
        if c == "#":
            return 1
    return 0


def walked_length(s: str):
    for c in s:
        pass
    n = len(s)
    if n >= 2:
        return 1
    return 0
