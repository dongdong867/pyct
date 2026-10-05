"""A split's count, linked back to its list: the int `len(parts)` returns for a split's list, and
what plain `+`, `-` and `*` made of it, so a fork that compares it with a plain int narrows the
list's length range (see ``core.spans``).

#121 writes such a compare as "is piece j there", exact on every string
(split-list-tracked-its-count-the-piece-there-or-the-input-s-own), so the lengths the fork
leaves hold on every input that records it. Any other list's `len(x)` compares never narrow its
range (forks-a-length-range-per-value-decides-its-checks-and-len-s-compares), so only a split's
list, or one the solver writes exactly from it, is linked.

The link holds only while the list is as it was when `len` read it: the same form and the same
length. A change the target makes since, through the list's methods or not, leaves the count
about a list that is gone, and it then narrows nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Protocol

from pyct.core.branch import Expression
from pyct.core.spans import Span, added, exactly, proves, scaled
from pyct.core.spans import narrowed as narrowed_span


class Counted(Protocol):
    """A tracked list a count reads: its form, its range and its length. It refuses a set, as
    the plain list does, so the range is written straight into its ``__dict__``."""

    expression: Expression | None
    span: Span

    def length(self) -> int: ...


@dataclass(frozen=True)
class Count:
    """An int that is ``scale * len(listed) + offset``, ``listed`` as it was at ``form`` with
    ``length`` items."""

    listed: Counted
    form: Expression
    length: int
    scale: int = 1
    offset: int = 0

    def through(self, op: str, number: int, *, reflected: bool) -> Count:
        """The count of ``self op number``, or of ``number op self`` when ``reflected``."""
        if op == "*":
            return replace(self, scale=self.scale * number, offset=self.offset * number)
        if op == "+":
            return replace(self, offset=self.offset + number)
        if reflected:
            return replace(self, scale=-self.scale, offset=number - self.offset)
        return replace(self, offset=self.offset - number)

    def current(self) -> bool:
        """Whether the list is still as it was when `len` read it."""
        listed = self.listed
        return listed.expression is self.form and listed.length() == self.length

    def span(self) -> Span | None:
        """The int's range, read from the list's range now; None once the list changed."""
        if not self.current():
            return None
        return added(scaled(self.listed.span, self.scale), exactly(self.offset))

    def narrow(self, op: str, number: int, taken: bool) -> None:
        """Narrow the list's range to the lengths that take ``taken`` on ``self op number``,
        recorded as a fork. A list that changed, a count that no longer reads the length, or a
        range that already answers the compare is left as it is."""
        span = self.span()
        if span is None or self.scale == 0 or proves(span, op, number) is not None:
            return
        fewest, most = narrowed_span(span, op, number, taken)
        lengths = _lengths(fewest, most, self.scale, self.offset)
        kept = _both(self.listed.span, lengths)
        if kept is not None:
            self.listed.__dict__["span"] = kept


def _lengths(fewest: int | None, most: int | None, scale: int, offset: int) -> Span:
    """The lengths whose ``scale * length + offset`` lies from ``fewest`` to ``most``, as a
    range: every such length is inside it."""
    if scale < 0:
        fewest, most = most, fewest
    low = None if fewest is None else -((offset - fewest) // scale)
    high = None if most is None else (most - offset) // scale
    return (max(low or 0, 0), high)


def _both(first: Span, second: Span) -> Span | None:
    """The lengths in both ranges; None when none is."""
    fewest = max(first[0] or 0, second[0] or 0)
    tops = [most for most in (first[1], second[1]) if most is not None]
    most = min(tops) if tops else None
    return None if most is not None and most < fewest else (fewest, most)
