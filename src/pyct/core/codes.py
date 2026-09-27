"""A tracked character's code and a tracked code's character: `ord` and `chr` where pyct binds them.

Python's `ord` and `chr` call no method of the value they are given, so a
tracked value's condition ends there unless the target's module calls
pyct's own (`pyct.core.bound`). Each raises on some
values, so each records the fork that decides it first, taken true when it
does not raise, as a division records its zero fork (``README.md › Rules ›
forks``). Python's own call then answers, or raises, marked as the target's.
"""

from __future__ import annotations

from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr, one_character
from pyct.core.values import forked, own

# the last code `chr` takes: U+10FFFF
LAST_CODE = 0x10FFFF

# Python's own, as this module loads: what `builtins` holds later is the target's business
_ORD, _CHR = ord, chr


def code(c: ConcolicStr) -> ConcolicInt:
    """`ord(c)`: the code of c's one character, carrying `["ord", c]`.

    `ord` takes exactly one character, so `["==", ["len", c], 1]` goes in
    first; on any other length Python's own `ord` raises its TypeError. A
    character an index, a walk or `chr` made (`ConcolicStr.single`) is one
    character on every path that reaches it, so it records no such fork.
    The solver would answer its flip unsat, but for `chr` of a code past
    U+2FFFF, the last character cvc5 holds, where it may answer an input that
    then leaves the plan, as `ord(chr(n))` does either way.
    """
    if not c.single:
        forked(c.sink, ["==", ["len", c.expression], 1], own(str.__len__, c) == 1)
    return ConcolicInt.made(own(_ORD, c), expression=["ord", c.expression], sink=c.sink)


def character(n: ConcolicInt) -> ConcolicStr:
    """`chr(n)`: the character of code n, carrying `["chr", n]`.

    `chr` takes a code from 0 to 1114111, so `[">=", n, 0]` goes in first
    and, when it holds, `["<=", n, 1114111]`; out of that range Python's own
    `chr` raises its ValueError.
    """
    value = own(int.__index__, n)
    if forked(n.sink, [">=", n.expression, 0], value >= 0):
        forked(n.sink, ["<=", n.expression, LAST_CODE], value <= LAST_CODE)
    return one_character(own(_CHR, n), ["chr", n.expression], n.sink)
