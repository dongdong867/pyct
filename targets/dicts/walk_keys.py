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


def grown_past_the_cap(d: dict[int, int]):
    for k in d:
        if d[k] > 5:
            if len(d) > 250:
                return 1
    return 0


def second_dict(d: dict[str, int], e: dict[str, int]):
    for k in d:
        if d[k] > 5:
            break
    e["zz"] = 0
    for j in e:
        if e[j] > 5 and "x" not in e:
            return 1
    return 0


def copied_out(d: dict[str, int]):
    out = {k: v + 1 for k, v in d.items()}
    if "a" in out:
        return 1
    return 0


def lowered(d: dict[str, int]):
    for k in d:
        if k.lower() == "admin":
            return 1
    return 0


def in_names(d: dict[str, int], names: list[str]):
    for k in d:
        if k in names:
            return 1
    return 0


from dataclasses import dataclass  # noqa: E402  here, so the lines above keep their numbers


@dataclass(frozen=True)
class Key:
    name: str


def keyed_set(d: dict[str, int]):
    held = {Key(k) for k in d}
    if Key("a") in held:
        return 1
    return 0


def keys_view(d: dict[str, int]):
    out = {k: v for k, v in d.items()}
    if out.keys() == {"a", "b"}:
        return 1
    return 0


def most(d: dict[int, int]):
    keys = [k for k in d]
    if keys and max(keys) > 100:
        return 1
    return 0
