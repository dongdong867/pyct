# the shapes a walk and a lookup after it take, each seeded with {"d": {"a": 1}} but `listed`,
# seeded with {"d": {"a": 0, "c": 0, "b": 0}}, and `bounded`, with {"d": {"a": 1}, "x": 1.0}


def sorted_walk(d: dict[str, int]):
    total = 0
    for k in sorted(d):
        total += d[k]
    if total > 5:
        return 1
    return 0


def listed_walk(d: dict[str, int]):
    for k in list(d):
        if d[k] > 5:
            return 1
    return 0


def literal_in_walk(d: dict[str, int]):
    for _ in d:
        if "a" in d:
            return 1
        return 2
    return 0


def listed(d: dict[str, int]):
    if "a" in d and "b" in d:
        if len(list(d)) == 2:
            return 1
        return 2
    return 0


def popped(d: dict[str, int]):
    d.popitem()
    if "z" in d:
        return 1
    return 2


def bounded(d: dict[str, int], x: float):
    for k in d:
        if d[k] > 5:
            return 3
    if x // 1.0 == 1e300:
        return 1
    return 2
