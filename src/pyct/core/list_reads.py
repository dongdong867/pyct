"""How a tracked list is read: at an index, and by a walk from either end.

An index records whether the list is long enough before Python may raise IndexError, as a
string's does: `[">", ["len", items], i]` for an index from the start and
`[">=", ["len", items], -i]` from the end. A tracked index records both, the first and then,
when it holds, `[">=", ["len", items], ["-", i]]`, together Python's `-len <= i < len`.

An item handed out is written as the target indexed it, `["[]", items, -1]` say, so it names
the last item of any input. An int or a str comes out tracked, and so does a float or a bool the
solver can type where it is read (``_typed_where_read``); a list inside, a None and every other
item come out as they are stored. An argument's float or bool stored there comes out after the
facts that hold what put it at that position, an index, a cut's start or a list's length, at its
value (``ListState.held``), so a fork on it holds where the run read it. A walk records
`[">", ["len", items], j]` for each item it takes and once more, taken false, where it ends.
Each such check on the length is a fact, not a fork, where the list's length range proves it
(``ListState.measure``, `core.spans`).

`len(items)` and `bool(items)` where pyct binds or routes them read the length term,
`["len", items]`, and record no fork where they run.
"""

from __future__ import annotations

import sys
import types
from collections.abc import Iterable, Iterator
from typing import Any, Protocol

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Expression, Fact, caller_site
from pyct.core.counts import Count
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.list_state import TRACKED, ListState, is_read, kind_of, plain
from pyct.core.spans import UNKNOWN, decided
from pyct.core.str_splits import JOIN_WALKS, a_split_s_list
from pyct.core.strs import ConcolicStr
from pyct.core.values import forked

# an int term that decides which of the argument's items a position reads, and its value now
type Pin = tuple[Expression, int]


def plain_index(key: object) -> int | None:
    """An index pyct writes as a number: a plain int, or a plain bool as the int it indexes with."""
    if type(key) is int or type(key) is bool:
        return int.__int__(key)
    return None


def long_enough(self: ListState, index: int, name: str = "__getitem__") -> bool:
    """Record whether the list holds a plain ``index``, and answer it: a fact where the list's
    range proves it, else a fork.

    Every operation that asks raises IndexError when the list does not hold
    it, so the check is the operation's before a raise.
    """
    length = self.length()
    if index >= 0:
        return self.measure(">", index, length > index, name, raising=True)
    return self.measure(">=", -index, length >= -index, name, raising=True)


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


def handed(
    self: ListState, position: int, written: Expression, name: str, index: int | None = None
) -> object:
    """The item at ``position``, handed out as the target indexed it with ``written``, a
    tracked index whose value is ``index``, or a plain one.

    An int or a str comes out tracked, as ``items[written]``, whatever else the list holds: the
    solver reads it by its position, by its list, or by what the path does with it. A float or
    a bool comes out so where the solver can type it, and else as it is stored, with the
    expression it came with (``_typed_where_read``), after the facts that hold what decides
    which of the argument's items the position reads (``ListState.held``), so a fork on it
    holds where the run read it. A list inside comes out as it is stored, since the target may
    change it where it sits; one still as its argument had it is named as the target indexed it
    (see ``_named``). A slot that no longer holds what pyct saw there is read plain, named
    ``name``.
    """
    if not self.holds(name, position):
        return plain(list.__getitem__(self, position))
    item = list.__getitem__(self, position)
    if isinstance(item, ListState):
        _named(self, item, written, index)
        return item
    kind = kind_of(item)
    if kind in _BY_PLACE and not _typed_where_read(self, written, kind):
        if position >= self.steady:
            _held_where_read(self, item)
        return item
    if kind not in TRACKED:
        return item
    value = plain(item)
    expression: Expression = ["[]", self.expression, written]
    if isinstance(value, float):
        return ConcolicFloat.made(value, expression=expression, sink=self.sink)
    if isinstance(value, bool):
        return ConcolicBool.made(value, expression=expression, sink=self.sink)
    if isinstance(value, str):
        return ConcolicStr.made(value, expression=expression, sink=self.sink)
    assert isinstance(value, int)
    return ConcolicInt.made(value, expression=expression, sink=self.sink)


# the kinds of item the solver types only by where a read lands or by its list's one kind: a path
# cannot say which of them a read is, since Python compares an int with a float
_BY_PLACE = frozenset({"float", "bool"})

# the kinds of item that have a term, against which a list holds one kind
_SCALARS = frozenset({"int", "str", "float", "bool"})


def _typed_where_read(self: ListState, written: Expression, kind: str) -> bool:
    """Whether the solver can type a float or a bool read from this list, as
    ``solver.list_kinds.ListTyping`` does (containers-a-float-or-bool-item-typed-by-place-or-one-
    kind-else-held-where-it-lands).

    An argument's list, or a list inside one at places the target wrote from the start, is
    typed by the input's kind at a plain position. Any other position of it, and any list built
    from it, is typed only when the list holds no other kind that has a term. A row a tracked
    index or one from the end picks is typed when every row holds that one kind, since the
    solver types it by every row's kinds (``ListState.picked``); a list built from such a row is
    not typed, since its own items may differ.
    """
    form = self.expression
    if is_read(form) and type(written) is int and _at_places(form):
        return True
    if self.picked is not None and is_read(form):
        return self.picked == {kind}
    return _built_at_places(form) and self.kinds & _SCALARS == {kind}


def _held_where_read(self: ListState, item: object) -> None:
    """Record, before an argument's float or bool comes out under its own place, that each term
    deciding which item the position reads has the value it has now: once for each term, since
    a fact holds for every fork after it."""
    if not isinstance(item, ConcolicFloat | ConcolicBool):
        return
    fields = self.__dict__
    for term, value in self.held[fields.get("told", 0) :]:
        self.sink.append(Fact(["==", term, value], True, caller_site()))
    fields["told"] = len(self.held)


# the heads that build a list from the lists among their first two operands
_BUILT = frozenset({"+", "*", "[:]"})


def _built_at_places(form: Expression) -> bool:
    """Whether each read of an argument's list a list's form builds on takes its steps at places
    the target wrote; a slice's start or a repeat's count that is such a read counts too."""
    if is_read(form):
        return _at_places(form)
    if not isinstance(form, list) or form[0] not in _BUILT:
        return True
    return all(_built_at_places(part) for part in form[1:3])


def _at_places(form: Expression) -> bool:
    """Whether a read of an argument's list takes each step at a key, or a position from the
    start, the target wrote."""
    step = form
    while isinstance(step, list):
        key = step[2]
        written = isinstance(key, str) and key.startswith(("'", '"'))
        if not written and not (type(key) is int and key >= 0):
            return False
        step = step[1]
    return True


def length(self: ListState) -> int:
    """`len(items)` where pyct binds `len`: the list's own length, carrying `["len", items]`,
    the same term the list's own forks read.

    Python's `len` makes what `__len__` hands back a plain int, so a tracked list's `__len__`
    stays a downgrade; this is what pyct's own `len` asks for instead (`pyct.core.bound.len`).
    The int carries the list's range as it is now (see ``ConcolicInt.span``), and a split's
    list's carries the list itself, whose range a compare with a plain int narrows
    (``core.counts``). A list with no form, or one whose form stopped describing it, gives its
    plain length. A length cannot fail, so it records no fork.
    """
    if not self.holds("__len__"):
        return self.length()
    measured = ConcolicInt.made(self.length(), expression=["len", self.expression], sink=self.sink)
    fields = measured.__dict__
    fields["span"] = self.span
    if a_split_s_list(self.expression):
        fields["count"] = Count(self, self.expression, self.length())
    return measured


def condition(self: ListState) -> Any:
    """`bool(items)` where pyct routes `bool`: the condition `if items:` tests, as a tracked bool
    that records no fork, so the fork is recorded where the target tests it.

    Python's `bool` tests the list on the spot, so this is what `pyct.core.bound.bool_` asks
    for instead. It holds the list's form at the call, which a later change replaces rather
    than edits. A list with no form, or one whose form stopped describing it, gives Python's
    plain answer, naming `__bool__` as `if items:` does. Where the list's range proves the
    answer, the fact is recorded here and the answer is a plain bool.
    """
    filled = self.length() != 0
    if not self.holds("__bool__"):
        return filled
    test: list[Expression] = ["!=", ["len", self.expression], 0]
    if decided(self.sink, self.span, test, filled):
        return filled
    return ConcolicBool.made(filled, test, self.sink)


def _named(self: ListState, row: ListState, written: Expression, index: int | None) -> None:
    """Name a list inside as the target indexed it, ``grid[-1]`` or ``grid[i]``, so its forks
    follow the outer list's length and the index, ``index`` the value of a tracked one.

    Only a list still as its argument had it, inside a list of lists still as the argument had
    it, is named again: a list the target changed keeps the form that builds it. A row picked
    by a tracked index or one from the end notes the kinds every row holds, which the solver
    types its reads by, and what picks it: the index, and the outer list's length for a
    position from the end.
    """
    if self.kinds != {"list"} or self.expression is None or row.expression is None:
        return
    if is_read(self.expression) and is_read(row.expression):
        wanted: Expression = ["[]", self.expression, written]
        if row.expression != wanted:
            # a check counts only for the length it was written on, so the row's range starts over
            fields = row.__dict__
            fields["expression"] = wanted
            fields["span"] = UNKNOWN
            moving = not (type(written) is int and written >= 0)
            fields["picked"] = _rows_kinds(self) if moving else None
            fields["held"], fields["told"] = _picking(self, written, index), 0
            fields["steady"] = 0 if fields["held"] else row.length()


def _rows_kinds(self: ListState) -> frozenset[str] | None:
    """The kinds with a term every row of an argument's list of rows holds, as the solver counts
    them for a row an index picks (``solver.list_kinds.of_rows``); None where the list is not
    read at places the target wrote, or a row is no longer as the argument had it."""
    rows = list.copy(self)
    if not _at_places(self.expression):
        return None
    if not all(isinstance(row, ListState) and is_read(row.expression) for row in rows):
        return None
    return frozenset().union(*(row.kinds for row in rows if isinstance(row, ListState))) & _SCALARS


def _picking(self: ListState, written: Expression, index: int | None) -> tuple[Pin, ...]:
    """What decides which row a position picks: a tracked index at its value, and the outer
    list's length where the position counts from the end."""
    length: Pin = (["len", self.expression], self.length())
    if index is not None:
        return ((written, index), length) if index < 0 else ((written, index),)
    return (length,) if type(written) is int and written < 0 else ()


def more(self: ListState, at: int, name: str) -> bool:
    """The walk's check for step ``at``: whether the list holds an item there, a fact where the
    list's range proves it, else a fork."""
    return self.measure(">", at, at < self.length(), name)


def walk(self: ListState) -> Iterator[object]:
    """``iter(items)``: each item in turn, one fork per item and one where the walk ends.

    The form is read afresh at each step, so a change the target makes while it walks is in the
    next fork. A change made without the list's methods turns the walk plain there, as it turns
    every other operation plain.

    The target's own loop over a split's list records no fork, as on origin/v2: a loop is
    Python's own walk of the pieces (``_a_split_s_loop``).
    """
    self.__dict__["walked_at"] = caller(2)
    if _a_split_s_loop(self):
        return list.__iter__(self)
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
    walk plain there; it then goes on as Python's own, from the position it had reached. The
    target's own loop over a split's list records no fork (``_a_split_s_loop``).
    """
    if _a_split_s_loop(self):
        return list.__reversed__(self)
    return _backward(self, self.length())


def _a_split_s_loop(self: ListState) -> bool:
    """Whether a walk of a split's list is Python's own: any walk but a join's of the list
    itself (``str_splits.JOIN_WALKS``): a loop, a comprehension, an unpacking, a builtin the
    target calls on it, ``map`` included, or a user ``__iter__`` a join reads. It records no
    "is there another piece" fork, as on origin/v2, by the user's decision
    (split-a-target-s-own-walk-records-no-piece-fork-a-fixed-count-unpack-forks-on-the-count);
    a join's walk of the list keeps its forks, which its encoding reads. An unpack into a fixed
    count records its count before it walks (``unpacking``)."""
    return a_split_s_list(self.expression) and JOIN_WALKS.get() is not self


def unpacking(self: ListState, op: str, number: int) -> object:
    """Record the count an unpack into a fixed number of places compares, before Python unpacks
    the list: `[op, ["len", items], number]`, ``op`` being ``==``, or ``>=`` with a star, and
    with a star, where that holds, `[">", ["len", items], number]`, whether the starred name's
    list holds anything, which Python builds plain. Answer what Python unpacks.

    Only a split's list records them, as `len(parts) == 2` written in the code would: a fact
    where its range decides it, else a fork that narrows the range, each marked as the unpack's
    own check. A list whose form no longer matches records nothing, and names no loss.
    Python's unpack of a split's list is the target's own walk, which records no piece fork
    (``_a_split_s_loop``), so it is handed its items as a plain list: the same items, and the
    error plain Python gives for that list, since from 3.14 Python counts the items of a plain
    list in its message and not those of a subclass. Any other list is walked here for an
    unpack with no star (``walked_for``), and handed back itself for one with a star, whose
    error Python words the same for a plain list and a subclass.
    """
    if not a_split_s_list(self.expression):
        return walked_for(self, number, list.copy(self)) if op == "==" else self
    length = self.length()
    if length == len(self.shadow):
        taken = length == number if op == "==" else length >= number
        self.measure(op, number, taken, "__iter__", raising=True)
        if op == ">=" and taken:
            self.measure(">", number, length > number, "__iter__", raising=True)
    return self.storage()


def walked_for(value: Iterable[object], number: int, held: list[object]) -> list[object]:
    """What Python is handed to unpack ``value`` into ``number`` places with no star: the items
    Python's own unpack would walk, at most ``number + 1``, walked here as it walks them, so
    the value records the same forks, then the items of ``held``, its plain items, past them,
    all in a plain list. From 3.14 Python counts a plain list's or dict's items in its "too
    many values" error and not a subclass's, so the error is plain Python's on every release.
    Only the forks' column moves, to the value's, where the unpack's call is, on every input
    alike."""
    walked = iter(value)
    taken = [item for _, item in zip(range(number + 1), walked, strict=False)]
    return taken + held[len(taken) :]


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


# the frames a call through the type puts between the code and the value's own method, which
# `pyct.core.type_calls` adds: `type(r).__len__(r)` is asked by the code that wrote it
CALLED_THROUGH: set[types.CodeType] = set()


def caller(depth: int) -> tuple[int, int]:
    """The frame ``depth`` calls up from here, and the instruction it runs.

    That is the code that called the list's own method, the target's or a library's; C code
    between the two leaves no frame, and a call through the type's frame is read past.
    """
    frame = sys._getframe(depth)
    while frame.f_code in CALLED_THROUGH and frame.f_back is not None:
        frame = frame.f_back
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
    started = self.walked_at
    # each refuses a set, as the plain value does: a list keeps the mark in its `__dict__`, a
    # range in a slot, and object's own set writes either
    object.__setattr__(self, "walked_at", None)
    # this function, then the value's `__len__`, then the code that asked
    return started is not None and started == caller(3)
