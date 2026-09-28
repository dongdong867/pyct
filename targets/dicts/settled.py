def only_a(d: dict[str, int]):
    for k in d:
        if d[k] > 5 and "a" not in d:
            return 1
    return 0


def int_only(d: dict[int, int]):
    for k in d:
        if d[k] > 5:
            if 1 not in d:
                return 1
    return 0
