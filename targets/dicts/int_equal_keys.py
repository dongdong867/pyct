import enum


class Color(enum.IntEnum):
    RED = 0


class OwnHash(int):
    def __hash__(self):
        return int.__hash__(self) + 0


def enum_key(d: dict[int, int]):
    if Color.RED in d:
        return 1
    if d:
        return 2
    return 0


def bool_keys(d: dict[int, int]):
    if True in d:
        return 1
    if d.get(False, 0) > 5:
        return 2
    if len(d) > 1:
        return 3
    return 0


def float_key(d: dict[int, int]):
    if 1.0 in d:
        return 1
    if len(d) > 1:
        return 2
    return 0


def own_hash_key(d: dict[int, int]):
    if OwnHash(0) in d:
        return 1
    if d:
        return 2
    return 0


def tracked_bool(b: bool, d: dict[int, int]):
    if b in d:
        return 1
    if d:
        return 2
    return 0


def stored_float(d: dict[int, int]):
    d[1.0] = 5
    if len(d) > 1:
        return 1
    return 0


def popped_bool(d: dict[int, int]):
    d.pop(True, None)
    if d:
        return 1
    return 0


def own_hash_stored(d: dict[int, int]):
    d[OwnHash(0)] = 5
    if len(d) > 1:
        return 1
    return 0
