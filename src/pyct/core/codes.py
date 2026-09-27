"""A tracked character's code and a tracked code's character: `ord` and `chr` where pyct binds them.

Python's `ord` and `chr` call no method of the value they are given, so a
tracked value's condition ends there unless the target's module calls
pyct's own (`substitutes.ord_`, `substitutes.chr_`). Each raises on some
values, so each records the fork that decides it first, taken true when it
does not raise, as a division records its zero fork (``README.md › Rules ›
forks``). Python's own call then answers, or raises, marked as the target's.
"""

from __future__ import annotations

from pyct.core.branch import Expression
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr
from pyct.core.values import forked, own

# the last code `chr` takes: U+10FFFF
LAST_CODE = 0x10FFFF


def code(c: ConcolicStr) -> ConcolicInt:
    """`ord(c)`: the code of c's one character, carrying `["ord", c]`.

    `ord` takes exactly one character, so `["==", ["len", c], 1]` goes in
    first; on any other length Python's own `ord` raises its TypeError. A
    character an index or a walk handed out, `["[]", s, i]`, is one
    character on every path that reaches it, so it records no such fork,
    which the solver could only answer unsat.
    """
    if not _indexed(c.expression):
        forked(c.sink, ["==", ["len", c.expression], 1], own(str.__len__, c) == 1)
    return ConcolicInt(own(ord, c), expression=["ord", c.expression], sink=c.sink)


def character(n: ConcolicInt) -> ConcolicStr:
    """`chr(n)`: the character of code n, carrying `["chr", n]`.

    `chr` takes a code from 0 to 1114111, so `[">=", n, 0]` goes in first
    and, when it holds, `["<=", n, 1114111]`; out of that range Python's own
    `chr` raises its ValueError.
    """
    value = own(int.__index__, n)
    if forked(n.sink, [">=", n.expression, 0], value >= 0):
        forked(n.sink, ["<=", n.expression, LAST_CODE], value <= LAST_CODE)
    return ConcolicStr(own(chr, n), expression=["chr", n.expression], sink=n.sink)


def _indexed(expression: Expression) -> bool:
    """Whether a string's expression is one character read at a position: `["[]", s, i]`."""
    return isinstance(expression, list) and expression[0] == "[]"
