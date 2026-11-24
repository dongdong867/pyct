"""Values lost at an operation pyct has not taught, at a call into code it cannot see inside,
and inside the standard library, for the summaries story summarize-a-lost-call."""

import io
import json
import re
import textwrap


def _quarter(n: int) -> int:
    return pow(n, 1, 4)


def shifted(n: int) -> str:
    k = _quarter(n)
    if k == 2:
        return "two"
    return "other"


def binned(n: int) -> str:
    t = bin(n)
    if t == "0b111":
        return "seven"
    return "other"


def squared(n: int) -> str:
    r = pow(n, 2, 10)
    if r == 9:
        return "nine"
    return "other"


def _bits(n: int) -> int:
    a = pow(n, 1, 2)
    b = pow(n, 1, 4)
    c = pow(n, 1, 8)
    del a, b, c
    return pow(n, 1, 16)


def deep(n: int) -> str:
    k = _bits(n)
    if k == 5:
        return "five"
    return "other"


def late(s: str, n: int) -> object:
    if io.StringIO(s).read(1) == "x":
        return "x"
    return pow(n, 1, 4)


def measured(s: str) -> str:
    if json.loads(s).get("k") == 7:
        return "seven"
    return "other"


def dedented(s: str) -> str:
    t = textwrap.dedent(s)
    if t == "ab":
        return "ab"
    return "other"


def wrapped(s: str) -> str:
    t = textwrap.fill(s, 10)
    if t == "ab":
        return "ab"
    return "other"


def matched(s: str) -> str:
    t = re.findall("a", s)
    if len(t) == 3:
        return "three"
    return "other"
