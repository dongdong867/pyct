def int_store(n: int, d: dict[int, int]):
    d[n] = 5
    if len(d) > 1:
        return "two"
    return "one"


def untyped_store(n, d):
    d[n] = 5
    if len(d) > 1:
        return "two"
    return "one"


def store_named(n: str, d: dict):
    d[n] = 5
    if "b" in d:
        return 1
    if n.startswith("b"):
        return 2
    return 0


def defaulted_named(n: str, d: dict):
    d.setdefault(n, 5)
    if "b" in d:
        return 1
    if n.startswith("b"):
        return 2
    return 0


def updated_named(n: str, d: dict):
    d.update({n: 5})
    if "b" in d:
        return 1
    if n.startswith("b"):
        return 2
    return 0


def merged_in_place_named(n: str, d: dict):
    d |= {n: 5}
    if "b" in d:
        return 1
    if n.startswith("b"):
        return 2
    return 0


def merged_named(n: str, d: dict):
    d = d | {n: 5}
    if "b" in d:
        return 1
    if n.startswith("b"):
        return 2
    return 0


def deleted(n: str, d: dict):
    del d[n]
    if "b" in d:
        if n.startswith("b"):
            return 2
        return 1
    return 0


def popped(n: str, d: dict):
    d.pop(n)
    if "b" in d:
        if n.startswith("b"):
            return 2
        return 1
    return 0


def popped_or_none(n: str, d: dict):
    d.pop(n, None)
    if "b" in d:
        if n.startswith("b"):
            return 2
        return 1
    return 0


def float_store(x: float, d: dict):
    d[x] = 1
    return "stored"


def missing_deleted(n: str, d: dict):
    del d[n]
    return len(d)


def missing_popped(n: str, d: dict):
    d.pop(n)
    return len(d)


def snapshot(n: str, d: dict):
    keys = list(d)
    d[n] = 0
    hits = 0
    for k in keys:
        if k in d:
            hits += 1
    if hits > 1:
        return "two"
    return "fewer"


def popped_then_stored(n: str, d: dict):
    if d:
        d.popitem()
    d[n] = 0
    if "a" in d:
        return "a"
    count = 0
    for k in d:
        count += 1
    if count > 1:
        return "more"
    return "one"


def own_walked(name: str, config: dict):
    config[name] = 0
    hits = 0
    for k in config:
        if k in config:
            hits += 1
    if hits > 1:
        return "two"
    if name == "q":
        return "q"
    return "one"


def own_walked_int(n: int, config: dict[int, int]):
    config[n] = 0
    hits = 0
    for k in config:
        if k in config:
            hits += 1
    if hits > 1:
        return "two"
    if n == 7:
        return "seven"
    return "one"


def rewalked(n: str, d: dict):
    keys = list(d)
    d.pop(n, None)
    for k in d:
        pass
    hits = 0
    for k in keys:
        if k in d:
            hits += 1
    if hits > 1:
        return "two"
    return "fewer"


def stored_through_walk(name: str, config: dict):
    config[name] = 0
    for k in list(config):
        config[k] = 1
    if name == "q":
        return "q"
    return "one"


def copied_walk(name: str, config: dict):
    config[name] = 0
    hits = 0
    for k in config.copy():
        if k in config:
            hits += 1
    if hits > 1:
        return "two"
    if name == "q":
        return "q"
    return "one"


def walked_then_read(n: str, d: dict):
    d[n] = 0
    for k in d:
        pass
    if "b" in d:
        return 1
    if n.startswith("b"):
        return 2
    return 0


def copy_looked_up(n: str, m: str, d: dict):
    c = d.copy()
    d[n] = 0
    for k in d:
        pass
    if m in c:
        return 1
    return 0
