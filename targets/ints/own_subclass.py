"""Forks against an int of the target's own subclass, which pyct writes as the plain int."""

import sys
from enum import IntEnum


def _mark(name: str) -> None:
    sys.stderr.write(f"TARGET CODE: {name} ran\n")


class Named(int):
    """An int whose repr is not a number."""

    def __repr__(self) -> str:
        return f"Named({int.__repr__(self)})"


class Marked(int):
    """An int that says so whenever one of its own methods runs."""

    def __repr__(self) -> str:
        _mark("__repr__")
        return int.__repr__(self)

    def __str__(self) -> str:
        _mark("__str__")
        return int.__repr__(self)

    def __format__(self, spec: str) -> str:
        _mark("__format__")
        return int.__format__(self, spec)

    def __int__(self) -> int:
        _mark("__int__")
        return int.__int__(self)

    def __index__(self) -> int:
        _mark("__index__")
        return int.__index__(self)

    def __lt__(self, other: object) -> bool:
        _mark("__lt__")
        return int.__lt__(self, other)  # pyrefly: ignore[bad-return]

    def __neg__(self) -> int:
        _mark("__neg__")
        return int.__neg__(self)


class Touchy(int):
    """An int whose text raises."""

    def __repr__(self) -> str:
        raise RuntimeError("Touchy has no text")

    def __str__(self) -> str:
        raise RuntimeError("Touchy has no text")


class Level(IntEnum):
    HIGH = 3


NAMED = Named(3)
MARKED = Marked(-3)
TOUCHY = Touchy(3)


def named(x: int) -> str:
    if x > NAMED:
        return "big"
    return "small"


def marked(x: int) -> str:
    if x > MARKED:
        return "big"
    return "small"


def touchy(x: int) -> str:
    if x > TOUCHY:
        return "big"
    return "small"


def level(x: int) -> str:
    if x + Level.HIGH > 5:
        return "high"
    return "low"
