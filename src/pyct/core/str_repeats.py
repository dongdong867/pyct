"""A tracked str repeated a plain number of times: `s * k` and `k * s`.

A count that is exactly an int or a bool, from 1 to `MOST_COPIES`, gives a
tracked str carrying ``["*", s, k]``, or ``["*", k, s]`` with the count on
the left, a bool's count written as the int it is; the solver writes it as k
copies of s joined. A count of zero or less gives Python's empty string,
which holds nothing of s, so it is plain and loses nothing. A larger count,
a tracked count and a count of any other type Python takes are str's own
answer and a downgrade named `__mul__` or `__rmul__`, as is any other
operand Python refuses, with Python's own error.
"""

from __future__ import annotations

import operator
from collections.abc import Callable
from typing import TYPE_CHECKING

from pyct.core.spans import repeated
from pyct.core.str_lengths import spanned
from pyct.core.values import downgraded, own

if TYPE_CHECKING:
    from pyct.core.strs import ConcolicStr

# the most copies of a string a repeat writes for the solver: past it some asks on the term ran
# to the solver's limit (decision str-repeat-by-a-plain-count-up-to-ten-written-as-its-copies)
MOST_COPIES = 10

_DOWNGRADES = {name: downgraded(str, name) for name in ("__mul__", "__rmul__")}


def _plain_times(s: ConcolicStr, count: object) -> object:
    return own(operator.mul, str.__str__(s), count)


def _plain_times_on_the_right(s: ConcolicStr, count: object) -> object:
    return own(operator.mul, count, str.__str__(s))


# a count Python cannot read as an int: Python's own `*` on the plain string, so the count's own
# method answers, or Python raises the error a plain str gives, which str's method does not
_REFUSALS = {
    "__mul__": downgraded(str, "__mul__", calling=_plain_times),
    "__rmul__": downgraded(str, "__rmul__", calling=_plain_times_on_the_right),
}


def _repeat(name: str) -> Callable[[ConcolicStr, object], object]:
    """The repeat by a count on one side: `__mul__` with the count on the right, `__rmul__` on
    the left, the side its form writes it on."""

    def repeat(s: ConcolicStr, count: object) -> object:
        if type(count) not in (int, bool) or count > MOST_COPIES:  # pyrefly: ignore[unsupported-operation]
            indexed = hasattr(type(count), "__index__")
            return (_DOWNGRADES if indexed else _REFUSALS)[name](s, count)
        copies = int.__index__(count)  # pyrefly: ignore[bad-argument-type]
        value = own(str.__mul__, s, copies)
        if copies <= 0:
            return value
        form = ["*", s.expression, copies] if name == "__mul__" else ["*", copies, s.expression]
        made = type(s).made(value, expression=form, sink=s.sink)
        return spanned(made, repeated(s.span, copies))

    return repeat


# ``s * count``, and ``count * s``, which Python hands to the str once the count's own `*` declines
times = _repeat("__mul__")
times_on_the_right = _repeat("__rmul__")
