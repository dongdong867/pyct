import decimal
import enum
import fractions


class Level(enum.IntEnum):
    LOW = 0


class Rate(float):
    pass


def fraction_key(d: dict[int, int]):
    if fractions.Fraction(0) in d:
        return 1
    if d:
        return 2
    return 0


def decimal_key(d: dict[int, int]):
    if decimal.Decimal(0) in d:
        return 1
    if d:
        return 2
    return 0


def float_subclass_key(d: dict[int, int]):
    if Rate(0.0) in d:
        return 1
    if d:
        return 2
    return 0


def defaulted_bool(d: dict[int, int]):
    d.setdefault(False, 5)
    if len(d) > 1:
        return 1
    return 0


def defaulted_enum(d: dict[int, int]):
    d.setdefault(Level.LOW, 5)
    if len(d) > 1:
        return 1
    return 0


def merged_after(d: dict[int, int]):
    joined = {True: 5} | d
    if len(joined) > 1:
        return 1
    return 0


def str_keyed_tracked_bool(b: bool, d: dict[int, int]):
    if b in d:
        return 1
    if len(d) > 1:
        return 2
    return 0
