# one change per function, each on a fresh copy of the argument, then a fork on the result.
# Seed each with {"a": 1, "b": 2}.


def assigned(config):
    c = config.copy()
    c["n"] = 7
    if len(c) > 2:
        return 1
    return 0


def deleted(config):
    c = config.copy()
    del c["a"]
    if len(c) > 0:
        return 1
    return 0


def popped(config):
    c = config.copy()
    v = c.pop("a")
    if v > 5:
        return 1
    return 0


def popped_last(config):
    c = config.copy()
    _, v = c.popitem()
    if v > 5:
        return 1
    return 0


def defaulted(config):
    c = config.copy()
    v = c.setdefault("n", 3)
    if v > 5:
        return 1
    return 0


def updated(config):
    c = config.copy()
    c.update({"n": 1})
    if len(c) > 2:
        return 1
    return 0


def copied(config):
    c = config.copy()
    if c["a"] > 5:
        return 1
    return 0


def merged(config):
    c = config | {"n": 1}
    if len(c) > 2:
        return 1
    return 0


def merged_in_place(config):
    c = config.copy()
    c |= {"n": 1}
    if len(c) > 2:
        return 1
    return 0


def keys(config):
    if "a" in config.copy().keys():
        return 1
    return 0


def values(config):
    if 5 in config.copy().values():
        return 1
    return 0


def items(config):
    for _, v in config.copy().items():
        if v > 5:
            return 1
    return 0


def reversed_keys(config):
    # the last item's value, read from the end: a lookup of a key a walk read would be a fork
    # whose other side no input takes
    c = config.copy()
    _, v = next(reversed(c.items()))
    if v > 5:
        return 1
    return 0
