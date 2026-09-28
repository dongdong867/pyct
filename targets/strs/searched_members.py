"""A tracked str searched among str subclass values, which Python compares on the element's left."""

from enum import Enum, StrEnum


class Color(StrEnum):
    RED = "red"
    BLUE = "blue"


class Mode(str, Enum):
    RED = "red"
    BLUE = "blue"


class Tag(str):
    pass


class Touchy(str):
    """A str that refuses to be compared."""

    def __eq__(self, other: object) -> bool:
        raise ValueError("no compare")

    __hash__ = str.__hash__


TAGS = [Tag("a"), Tag("b")]


def colors(s: str) -> str:
    if s in (Color.RED, Color.BLUE):
        return "known"
    return "unknown"


def modes(s: str) -> str:
    if s in [Mode.RED, Mode.BLUE]:
        return "known"
    return "unknown"


def not_tagged(s: str) -> str:
    if s not in TAGS:
        return "new"
    return "tagged"


def itself(s: str) -> str:
    if s in (s, Color.RED):
        return "found"
    return "missing"


def touchy(s: str) -> str:
    if s in (Color.RED, Touchy("b")):
        return "found"
    return "missing"
