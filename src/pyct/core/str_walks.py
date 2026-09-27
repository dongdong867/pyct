"""A walk over a tracked str: `for c in s`, and everything else that iterates s.

Each pass records a fork saying s has a character at that position,
``[">", ["len", s], i]``, taken true, and the pass after the last records the
same fork taken false: the walk's exit. Flipping the exit asks for a longer
string, and flipping an earlier pass a shorter one
(``README.md › Rules › forks``).
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING

from pyct.core.branch import Expression
from pyct.core.values import forked, own

if TYPE_CHECKING:
    from pyct.core.strs import ConcolicStr


def walk(s: ConcolicStr) -> Iterator[ConcolicStr]:
    """s's characters, each a tracked str carrying ``["[]", s, i]``, as indexing hands it out.

    A pass's fork is recorded when Python asks for the next character, so it
    sits where the walk runs: a loop's fork at the iterable's column, as
    Python places the loop's step, and a call such as ``zip(s, t)`` or
    ``list(s)`` at the call. The pass's fork already says position i
    exists, so a character records no long-enough fork of its own. str's own
    length, not ``len(s)``, which would record ``__len__``.
    """
    length = own(str.__len__, s)
    measured: Expression = ["len", s.expression]
    at = 0
    while forked(s.sink, [">", measured, at], at < length):
        character = type(s)(
            own(str.__getitem__, s, at), expression=["[]", s.expression, at], sink=s.sink
        )
        # one character on every pass: the pass's fork says position i exists
        character.single = True
        yield character
        at += 1
