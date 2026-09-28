"""A tracked int searched among int subclass values, which Python compares on the element's left."""

from enum import IntEnum


class Status(IntEnum):
    OK = 0
    BAD = 1


class Level(IntEnum):
    LOW = 1
    HIGH = 3


class Odd(int):
    """An int equal to every odd number, by its own `__eq__`."""

    def __eq__(self, other: object) -> bool:
        return int(other) % 2 == 1  # pyrefly: ignore[bad-argument-type]

    __hash__ = int.__hash__


class Touchy(int):
    """An int that refuses to be compared."""

    def __eq__(self, other: object) -> bool:
        raise ValueError("no compare")

    __hash__ = int.__hash__


KNOWN = [Level.LOW, Level.HIGH]


def members(x: int) -> str:
    if x in (Status.OK, Status.BAD):
        return "known"
    return "unknown"


def not_known(x: int) -> str:
    if x not in KNOWN:
        return "new"
    return "known"


def bools(x: int) -> str:
    if x in (True, 3):
        return "found"
    return "missing"


def chained(x: int) -> str:
    if 0 <= x in (Status.OK, Status.BAD):
        return "known"
    return "unknown"


def odd(x: int) -> str:
    if x in (Odd(1),):
        return "odd"
    return "even"


def itself(x: int) -> str:
    if x in (x, Status.OK):
        return "found"
    return "missing"


def touchy(x: int) -> str:
    if x in (Status.OK, Touchy(1)):
        return "found"
    return "missing"
