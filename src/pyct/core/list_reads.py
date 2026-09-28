"""How a tracked list is read: at an index, and by a walk from either end.

An index records whether the list is long enough before Python may raise IndexError, as a
string's does: `[">", ["len", items], i]` for an index from the start and
`[">=", ["len", items], -i]` from the end. A tracked index records both, the first and then,
when it holds, `[">=", ["len", items], ["-", i]]`, together Python's `-len <= i < len`.

An item handed out is written as the target indexed it, `["[]", items, -1]` say, so it names
the last item of any input. An int or a str comes out tracked; a list inside, a None and every
other item come out as they are stored. A walk records `[">", ["len", items], j]` for each item
it takes and once more, taken false, where it ends.

`len(items)` and `bool(items)` where pyct binds or routes them read the length term,
`["len", items]`, and record no fork where they run.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from typing import Any, Protocol

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Expression
from pyct.core.ints import ConcolicInt
from pyct.core.list_state import TRACKED, ListState, is_read, kind_of, plain
from pyct.core.strs import ConcolicStr
from pyct.core.values import forked


def plain_index(key: object) -> int | None:
    """An index pyct writes as a number: a plain int, or a plain bool as the int it indexes with."""
    if type(key) is int or type(key) is bool:
        return int.__int__(key)
    return None


def long_enough(self: ListState, index: int, name: str = "__getitem__") -> bool:
    """Record whether the list holds a plain ``index``, and answer it.

    Every operation that asks raises IndexError when the list does not hold
    it, so the fork is the operation's before a raise.
    """
    measured: Expression = ["len", self.expression]
    length = self.length()
    if index >= 0:
        return forked(self.sink, [">", measured, index], length > index, name, raising=True)
    return forked(self.sink, [">=", measured, -index], length >= -index, name, raising=True)


def tracked_long_enough(self: ListState, index: ConcolicInt, name: str = "__getitem__") -> bool:
    """Record whether the list holds a tracked ``index``, in two forks, and answer it."""
    measured: Expression = ["len", self.expression]
    value = int.__int__(index)
    length = self.length()
    if not forked(self.sink, [">", measured, index.expression], length > value, name, raising=True):
        return False
    return forked(
        self.sink, [">=", measured, ["-", index.expression]], length >= -value, name, raising=True
    )


def handed(self: ListState, position: int, written: Expression, name: str) -> object:
    """The item at ``position``, handed out as the target indexed it with ``written``.

    An int or a str comes out tracked, as ``items[written]``, whatever else the list holds: the
    solver reads it by its position, by its list, or by what the path does with it. A list
    inside comes out as it is stored, since the target may change it where it sits; one still
    as its argument had it is named as the target indexed it (see ``_named``). A slot that no
    longer holds what pyct saw there is read plain, named ``name``.
    """
    if not self.holds(name, position):
        return plain(list.__getitem__(self, position))
    item = list.__getitem__(self, position)
    if isinstance(item, ListState):
        _named(self, item, written)
        return item
    if kind_of(item) not in TRACKED:
        return item
    value = plain(item)
    expression: Expression = ["[]", self.expression, written]
    if isinstance(value, str):
        return ConcolicStr.made(value, expression=expression, sink=self.sink)
    assert isinstance(value, int)
    return ConcolicInt.made(value, expression=expression, sink=self.sink)


def length(self: ListState) -> int:
    """`len(items)` where pyct binds `len`: the list's own length, carrying `["len", items]`,
    the same term the list's own forks read.

    Python's `len` makes what `__len__` hands back a plain int, so a tracked list's `__len__`
    stays a downgrade; this is what pyct's own `len` asks for instead (`pyct.core.bound.len`).
    A list with no form, or one whose form stopped describing it, gives its plain length. A
    length cannot fail, so it records no fork.
    """
    if not self.holds("__len__"):
        return self.length()
    return ConcolicInt.made(self.length(), expression=["len", self.expression], sink=self.sink)


def condition(self: ListState) -> Any:
    """`bool(items)` where pyct routes `bool`: the condition `if items:` tests, as a tracked bool
    that records no fork, so the fork is recorded where the target tests it.

    Python's `bool` tests the list on the spot, so this is what `pyct.core.bound.bool_` asks
    for instead. It holds the list's form at the call, which a later change replaces rather
    than edits. A list with no form, or one whose form stopped describing it, gives Python's
    plain answer, naming `__bool__` as `if items:` does.
    """
    filled = self.length() != 0
    if not self.holds("__bool__"):
        return filled
    return ConcolicBool.made(filled, ["!=", ["len", self.expression], 0], self.sink)


def _named(self: ListState, row: ListState, written: Expression) -> None:
    """Name a list inside as the target indexed it, ``grid[-1]`` or ``grid[i]``, so its forks
    follow the outer list's length and the index.

    Only a list still as its argument had it, inside a list of lists still as the argument had
    it, is named again: a list the target changed keeps the form that builds it.
    """
    if self.kinds != {"list"} or self.expression is None or row.expression is None:
        return
    if is_read(self.expression) and is_read(row.expression):
        wanted: Expression = ["[]", self.expression, written]
        if row.expression != wanted:
            row.expression = wanted


def more(self: ListState, at: int, name: str) -> bool:
    """The walk's fork for step ``at``: whether the list holds an item there."""
    return forked(self.sink, [">", ["len", self.expression], at], at < self.length(), name)


def walk(self: ListState) -> Iterator[object]:
    """``iter(items)``: each item in turn, one fork per item and one where the walk ends.

    The form is read afresh at each step, so a change the target makes while it walks is in the
    next fork. A change made without the list's methods turns the walk plain there, as it turns
    every other operation plain.
    """
    self.walked_at = caller(2)
    return _walked(self)


def _walked(self: ListState) -> Iterator[object]:
    at = 0
    while self.holds("__iter__", at):
        if not more(self, at, "__iter__"):
            return
        yield handed(self, at, at, "__iter__")
        at += 1
    while at < self.length():
        yield list.__getitem__(self, at)
        at += 1


def backward(self: ListState) -> Iterator[object]:
    """``reversed(items)``: each item from the end, one fork per item and one where it ends.

    The item j steps from the end is written ``items[-(j + 1)]``, so it follows the length. A
    change to the length while it walks, or one made without the list's methods, turns the
    walk plain there; it then goes on as Python's own, from the position it had reached.
    """
    return _backward(self, self.length())


def _backward(self: ListState, size: int) -> Iterator[object]:
    step = 0
    while self.holds("__reversed__", size - 1 - step) and self.length() == size:
        if not more(self, step, "__reversed__"):
            return
        yield handed(self, size - 1 - step, -(step + 1), "__reversed__")
        step += 1
    if self.expression is not None:
        self.lose("__reversed__")
    for at in range(size - 1 - step, -1, -1):
        if at < self.length():
            yield list.__getitem__(self, at)


def caller(depth: int) -> tuple[int, int]:
    """The frame ``depth`` calls up from here, and the instruction it runs.

    That is the code that called the list's own method, the target's or a library's; C code
    between the two leaves no frame.
    """
    frame = sys._getframe(depth)
    return id(frame), frame.f_lasti


class Walked(Protocol):
    """A tracked value a walk starts on: where the last walk started, until its size is asked."""

    walked_at: tuple[int, int] | None


def hinted(self: Walked) -> bool:
    """Whether a `__len__` call is Python's own guess at the size of a walk it just started.

    `list(items)`, `sorted`, `tuple` and `str.join` start a walk and then ask the length only
    to size what they build, in the same call of the same code. Only the first ask after a
    walk starts can be that guess. A tracked list and a tracked range each ask it.
    """
    started, self.walked_at = self.walked_at, None
    # this function, then the value's `__len__`, then the code that asked
    return started is not None and started == caller(3)
