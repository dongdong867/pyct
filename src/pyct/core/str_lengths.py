"""A tracked string's length: `len(s)`, and the range a string keeps of it.

A string holds the fewest and the most characters it has on every input that takes the path
(decision forks-a-length-range-per-value-decides-its-checks-and-len-s-compares): a character an
index, a walk or `chr` handed out holds one, a concatenation the sum of its parts, a slice with
plain bounds what Python's clamp leaves, and any other string zero or more. Its walks narrow
the range and are decided by it (see `str_walks`); its truth test and a plain index's
long-enough check stay forks, and narrow it.
"""

from __future__ import annotations

from pyct.core.ints import ConcolicInt
from pyct.core.spans import UNKNOWN, Span, exactly, narrowed, sliced
from pyct.core.str_cases import Tracked
from pyct.core.values import own


def length(s: Tracked) -> ConcolicInt:
    """`len(s)` where pyct binds `len`: str's own length, carrying `["len", s]`.

    Python's `len` makes what `__len__` hands back a plain int, so a
    tracked string's `__len__` stays a downgrade; this is what pyct's own
    `len` asks for instead (`pyct.core.bound.len`). The int carries the
    string's range as it is now (see ``ConcolicInt.span``). A length cannot
    fail, so it records no fork.
    """
    measured = ConcolicInt.made(own(str.__len__, s), expression=["len", s.expression], sink=s.sink)
    measured.__dict__["span"] = s.span
    return measured


def cut(s: Tracked, key: slice) -> Span:
    """The range of a slice of ``s``: Python's clamp of its range for plain bounds and step,
    and none from the form for a tracked one, which may cut another number on another input."""
    ends = (key.start, key.stop, key.step)
    if not all(end is None or type(end) is int for end in ends):
        return UNKNOWN
    return sliced(s.span, key.start, key.stop, key.step)


def of_other(s: Tracked, other: object) -> Span:
    """The range of a string joined to ``s``: a tracked one's own, on this path, and a plain
    one's its length. A tracked string kept from an earlier call carries that call's path."""
    span = getattr(other, "span", None)
    if span is None:
        return exactly(str.__len__(other))  # pyrefly: ignore[bad-argument-type]
    return span if getattr(other, "sink", None) is s.sink else UNKNOWN


def spanned[T: Tracked](s: T, span: Span) -> T:
    """``s``, a string pyct just built, holding ``span``. A str refuses a set, as a plain one
    does, so the range is written straight into its ``__dict__``."""
    s.__dict__["span"] = span
    return s


def tested(s: Tracked, filled: bool) -> bool:
    """Narrow the range of ``s`` by its truth test, which found it ``filled`` or not: the fork
    stays, and the answer comes back."""
    s.__dict__["span"] = narrowed(s.span, "!=", 0, filled)
    return filled
