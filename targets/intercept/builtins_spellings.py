import builtins as b
from builtins import chr
from builtins import len as size


def code(c: str) -> str:
    if b.ord(c) == 97:
        return "a"
    return "other"


def sized(s: str) -> str:
    if size(s) > 3:
        return "long"
    return "short"


def character(n: int) -> str:
    if chr(n) == "A":
        return "A"
    return "other"
