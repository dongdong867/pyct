"""How a tracked list is read: at an index, and by a walk from either end.

An index records whether the list is long enough before Python may raise IndexError, as a
string's does: `[">", ["len", items], i]` for an index from the start and
`[">=", ["len", items], -i]` from the end. A tracked index records both, the first and then,
when it holds, `[">=", ["len", items], ["-", i]]`, together Python's `-len <= i < len`.

An item handed out is written as the target indexed it, `["[]", items, -1]` say, so it names
the last item of any input. An int or a str comes out tracked; a list inside, a None and every
other item come out as they are stored. A walk records `[">", ["len", items], j]` for each item
it takes and once more, taken false, where it ends.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator

from pyct.core.branch import Downgrade, Expression
from pyct.core.ints import ConcolicInt
from pyct.core.list_state import TRACKED, ListState, kind_of
from pyct.core.strs import ConcolicStr
from pyct.core.values import forked

# the type that tracks each kind of item a read hands out
_TRACKED_TYPES: dict[str, type[ConcolicInt] | type[ConcolicStr]] = {
    "int": ConcolicInt,
    "str": ConcolicStr,
}

# the plain value of a tracked item, read from its base type so nothing is recorded
_PLAIN: dict[str, Callable[[object], object]] = {"int": int.__int__, "str": str.__str__}


def plain_index(key: object) -> int | None:
    """An index pyct writes as a number: a plain int, or a plain bool as the int it indexes with."""
    if type(key) is int or type(key) is bool:
        return int.__int__(key)  # type: ignore[arg-type]
    return None


def long_enough(self: ListState, index: int) -> bool:
    """Record whether the list holds a plain ``index``, and answer it."""
    measured: Expression = ["len", self.expression]
    length = self.length()
    if index >= 0:
        return forked(self.sink, [">", measured, index], length > index)
    return forked(self.sink, [">=", measured, -index], length >= -index)


def tracked_long_enough(self: ListState, index: ConcolicInt) -> bool:
    """Record whether the list holds a tracked ``index``, in two forks, and answer it."""
    measured: Expression = ["len", self.expression]
    value = int.__int__(index)
    length = self.length()
    if not forked(self.sink, [">", measured, index.expression], length > value):
        return False
    return forked(self.sink, [">=", measured, ["-", index.expression]], length >= -value)


def handed(self: ListState, position: int, written: Expression, name: str) -> object:
    """The item at ``position``, handed out as the target indexed it with ``written``.

    An int or a str comes out tracked when the solver can tell its kind from the form: a
    position from the start of an argument's own list, or a list whose items share that kind.
    Past that it is a downgrade named ``name``, and the item comes out plain.
    """
    item = list.__getitem__(self, position)
    kind = kind_of(item)
    if kind not in TRACKED:
        return item
    plain = _PLAIN[kind](item)
    by_position = self.static() and type(written) is int and written >= 0
    if not by_position and self.kinds & TRACKED != {kind}:
        self.sink.append(Downgrade(name=name))
        return plain
    expression: Expression = ["[]", self.expression, written]
    return _TRACKED_TYPES[kind](plain, expression=expression, sink=self.sink)


def more(self: ListState, at: int) -> bool:
    """The walk's fork for step ``at``: whether the list holds an item there."""
    return forked(self.sink, [">", ["len", self.expression], at], at < self.length())


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
        if not more(self, at):
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
        if not more(self, step):
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


def hinted(self: ListState) -> bool:
    """Whether a `__len__` call is Python's own guess at the size of a walk it just started.

    `list(items)`, `sorted`, `tuple` and `str.join` start a walk and then ask the length only
    to size what they build, in the same call of the same code. Only the first ask after a
    walk starts can be that guess.
    """
    started, self.walked_at = self.walked_at, None
    # this function, then the list's `__len__`, then the code that asked
    return started is not None and started == caller(3)
