"""How a tracked list is searched and compared: item by item, as Python does it.

`x in items`, `index`, `count` and `remove` take the items by a walk and compare each with
`x`, `["==", ["[]", items, j], x]`, each compare a fork where the operation runs. Two lists
compare as Python compares them: `==` checks the lengths first, `["==", ["len", items], 2]`,
then each pair until one differs; an order finds the first pair that differs the same way and
answers with that pair's own compare, or with the lengths' when one list runs out first. A
length check the lists' ranges prove is a fact, not a fork (`core.spans`).
"""

from __future__ import annotations

import operator
from collections.abc import Callable
from typing import Any

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Expression
from pyct.core.list_reads import handed, more
from pyct.core.list_state import ListState
from pyct.core.spans import Span, added, proves, scaled
from pyct.core.values import forked, held, own

# Python's order on two lists, by the operator's head
ORDERS: dict[str, Callable[[Any, Any], Any]] = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
}


def matches(item: object, other: object) -> bool:
    """Whether two items are equal as a list finds it: the same object, or `==` held.

    Testing the answer for truth is what records the fork on a tracked item.
    """
    return item is other or own(bool, own(operator.eq, item, other))


def searched(self: ListState, value: object, name: str, *, every: bool = False) -> list[int]:
    """The positions of the items equal to ``value``, found as Python searches the list.

    Each item is taken by a walk step and compared, each compare a fork. The search stops at
    the first match unless ``every``. A change made without the list's methods turns the
    search plain from the position it reached, as Python's own.
    """
    found: list[int] = []
    at = 0
    while self.holds(name, at):
        if not more(self, at, name):
            return found
        if matches(handed(self, at, at, name), value):
            found.append(at)
            if not every:
                return found
        at += 1
    while at < self.length():
        if matches(list.__getitem__(self, at), value):
            found.append(at)
            if not every:
                return found
        at += 1
    return found


class _Side:
    """One side of a compare between two lists: its length and its items, as a compare reads them.

    A side is tracked while its form describes it; a change made without its methods turns it
    plain at the position that shows it, and from there it reads as a plain list.
    """

    def __init__(self, value: list[object], name: str) -> None:
        self.value = value
        self.name = name

    def form(self) -> ListState | None:
        """The side as a tracked list, while its form holds: its length checked each time, so
        a change made without its methods turns it plain before a fork reads its form."""
        value = self.value
        return value if isinstance(value, ListState) and value.holds(self.name) else None

    def size(self) -> Expression:
        """The length as a compare writes it: `["len", form]` for a tracked list, else the int."""
        tracked = self.form()
        return list.__len__(self.value) if tracked is None else ["len", tracked.expression]

    def span(self, owner: ListState) -> Span:
        """The length's range, as the list ``owner`` reads another it is compared with."""
        return owner.span_of(self.value)

    def has(self, at: int) -> bool:
        """Whether this side holds an item at ``at``, a fork when it is tracked."""
        tracked = self.form()
        if tracked is not None:
            return more(tracked, at, self.name)
        return at < list.__len__(self.value)

    def item(self, at: int) -> object:
        """The item at ``at``, handed out as a read of the form while it holds."""
        tracked = self.form()
        if tracked is not None and tracked.holds(self.name, at):
            return handed(tracked, at, at, self.name)
        return list.__getitem__(self.value, at)


def equal(self: ListState, other: list[object], name: str) -> bool:
    """``self == other`` as Python answers it: the lengths first, then each pair in turn."""
    left, right = _Side(self, name), _Side(other, name)
    same = self.length() == list.__len__(other)
    if not _same_length(self, left, right, same, name):
        return False
    return all(matches(left.item(at), right.item(at)) for at in range(self.length()))


def _same_length(self: ListState, left: _Side, right: _Side, same: bool, name: str) -> bool:
    """The length check a compare for equality makes first: against a plain list's length, on
    this list's range; against another tracked list's, a fact only where both ranges prove it,
    and a fork that narrows neither, since it is written on two lengths."""
    theirs = right.size()
    if type(theirs) is int:
        return self.measure("==", theirs, same, name)
    test: Expression = ["==", left.size(), theirs]
    if apart(left.span(self), right.span(self), "==") is same:
        return held(self.sink, test, same, name)
    return forked(self.sink, test, same, name)


def apart(left: Span, right: Span, op: str) -> bool | None:
    """What two lengths' ranges say of ``left op right``: their difference's range against 0."""
    return proves(added(left, scaled(right, -1)), op, 0)


def ordered(self: ListState, other: list[object], op: str) -> object:
    """``self < other`` and the other orders as Python answers them.

    The first pair that differs answers with its own compare, which the target tests; when one
    list runs out first, the lengths answer, as a tracked bool when either length is tracked.
    """
    name = f"__{_NAMES[op]}__"
    left, right = _Side(self, name), _Side(other, name)
    at = 0
    while left.has(at) and right.has(at):
        mine, theirs = left.item(at), right.item(at)
        if not matches(mine, theirs):
            return own(ORDERS[op], mine, theirs)
        at += 1
    answer = bool(own(ORDERS[op], self.length(), list.__len__(other)))
    ran_out = ConcolicBool.made(answer, expression=[op, left.size(), right.size()], sink=self.sink)
    if apart(left.span(self), right.span(self), op) is answer:
        # the ranges prove which list runs out first: where the target tests it, a fact
        ran_out.__dict__["decided"] = True
    return ran_out


_NAMES = {"<": "lt", "<=": "le", ">": "gt", ">=": "ge"}
