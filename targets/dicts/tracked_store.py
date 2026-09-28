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


def walked(n: str, d: dict):
    d[n] = 0
    count = 0
    for k in d:
        count += 1
    if count > 1:
        return "more"
    return "one"


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


def plain_walked(d: dict):
    d["x"] = 5
    count = 0
    for k in d:
        count += 1
    if count > 1:
        return "more"
    return "one"
