"""How a tracked list changes: each change Python makes, and the form it leaves behind.

Every change runs Python's own operation on the items, through `own`, so what it takes, what it
refuses and what it raises are Python's, and then the same operation on the shadow, so the
shadow keeps what pyct saw. Beside them the form becomes the expression the change writes (see
`list_forms`). A change pyct cannot write, a value no expression holds or a form of the
operation it does not follow, is a downgrade named by the operation: Python makes the change
and the list is plain from then on.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pyct.core.branch import Expression
from pyct.core.ints import ConcolicInt
from pyct.core.list_forms import (
    UNWRITTEN,
    displayed,
    dropped,
    joined,
    placed,
    put,
    spliced,
    written,
)
from pyct.core.list_reads import handed, long_enough, plain_index, tracked_long_enough
from pyct.core.list_state import ListState, kind_of, kinds_of, plain
from pyct.core.str_splits import built_from_a_split
from pyct.core.values import forked, own

# one change, made the same way on the items and on the shadow
type Change = Callable[[list[object]], object]


def position(key: object) -> Expression | None:
    """An index or a slice bound as the form writes it, or None when pyct does not follow it.

    A plain int or bool is itself and a tracked int its expression. A compare's answer and
    every other kind of value are not followed.
    """
    index = plain_index(key)
    if index is not None:
        return index
    return key.expression if type(key) is ConcolicInt else None


def follows(self: ListState, key: object) -> bool:
    """Whether pyct follows an index into this list: a plain one, or a tracked one into a list
    whose items share a kind (containers-arrays-counted-keys-and-copied-walk-keys) and that is
    not made from a split's (follow-the-length-of-a-split)."""
    if type(key) is ConcolicInt:
        return len(self.kinds) <= 1 and not built_from_a_split(self.expression)
    return plain_index(key) is not None


def in_range(self: ListState, key: object, name: str = "__getitem__") -> bool:
    """Record whether the list holds the index ``key``, as the index's own kind records it."""
    if type(key) is ConcolicInt:
        return tracked_long_enough(self, key, name)
    return long_enough(self, _number(key), name)


def resolved(self: ListState, key: object) -> int:
    """The position an index in range reads: a negative one counts back from the end."""
    index = _number(key)
    return index + self.length() if index < 0 else index


def _number(key: object) -> int:
    """The plain value of an index pyct follows, read from int itself so nothing is recorded."""
    assert isinstance(key, int)
    return int.__int__(key)


def made(self: ListState, change: Change, form: Expression, kinds: frozenset[str]) -> object:
    """Make a change Python's own way, then on the shadow, and take on its form."""
    answer = own(change, self)
    change(self.shadow)
    fields = self.__dict__
    fields["expression"] = form
    fields["kinds"] = self.kinds | kinds
    return answer


def unfollowed(self: ListState, name: str, change: Change) -> object:
    """A change pyct does not follow: Python makes it, and the list is plain from then on.

    A change that raises changes nothing, so it records nothing. The loss is named unless the
    list was plain already.
    """
    answer = own(change, self)
    if self.expression is not None:
        self.lose(name)
    return plain(answer)


def added(value: list[object], name: str) -> tuple[Expression, frozenset[str]] | None:
    """The form and the kinds of a list another list takes in: its own form, or a display.

    None for a list that holds a value no expression holds. A tracked list whose form no longer
    holds is read as the plain list it is, named by ``name``.
    """
    if isinstance(value, ListState) and value.holds(name):
        return value.expression, value.kinds
    items = list.copy(value)
    form = displayed(items, name)
    return None if form is UNWRITTEN else (form, kinds_of(items))


def taken_in(
    values: object, name: str
) -> tuple[list[object], tuple[Expression, frozenset[str]] | None]:
    """What ``extend``, ``+=`` and a slice assignment take in: the items, and their form.

    Python reads any iterable once; a list is read in C, so a tracked one is not walked, and
    any other iterable is read into a list first, as Python reads it.
    """
    if isinstance(values, list):
        return list.copy(values), added(values, name)
    items = own(list, values)
    return items, added(items, name)


def append(self: ListState, value: object) -> None:
    """``items.append(x)``: the list becomes ``items + [x]``."""
    form = written(value, "append")
    change: Change = lambda items: list.append(items, value)  # noqa: E731
    if form is UNWRITTEN or not self.holds("append"):
        unfollowed(self, "append", change)
        return
    made(self, change, joined(self.expression, ["[,]", form]), frozenset({kind_of(value)}))


def extend(self: ListState, values: object, name: str = "extend") -> None:
    """``items.extend(ys)`` and ``items += ys``: the list becomes ``items + ys``.

    Python reads a non-list iterable once, so it is read into a list here and that list is
    what both the items and the form take in.
    """
    taken, other = taken_in(values, name)
    change: Change = lambda items: list.extend(items, taken)  # noqa: E731
    if other is None or not self.holds(name):
        unfollowed(self, name, change)
        return
    form, kinds = other
    made(self, change, joined(self.expression, form), kinds)


def insert(self: ListState, index: Any, value: object) -> None:
    """``items.insert(i, x)``: the list becomes ``items[:i] + [x] + items[i:]``.

    Insert clamps its position to the list, so it records no fork.
    """
    at, form = position(index), written(value, "insert")
    change: Change = lambda items: list.insert(items, index, value)  # noqa: E731
    if at is None or form is UNWRITTEN or not self.holds("insert"):
        unfollowed(self, "insert", change)
        return
    made(self, change, placed(self.expression, at, form), frozenset({kind_of(value)}))


def pop(self: ListState, *args: Any) -> object:
    """``items.pop()`` and ``items.pop(i)``, handing out the item as indexed.

    ``pop()`` records that the list is not empty, and ``pop(i)`` the index's long-enough fork,
    each before Python may raise IndexError. The list becomes ``items[:-1]``, or
    ``items[:i] + items[i:][1:]``.
    """
    key = args[0] if args else -1
    if len(args) > 1 or not follows(self, key) or not self.holds("pop"):
        return unfollowed(self, "pop", lambda items: list.pop(items, *args))
    if not _pops(self, key, bool(args)):
        return own(list.pop, self, *args)
    at = resolved(self, key)
    if not self.holds("pop", at):
        # the slot no longer holds what pyct saw there: the list is plain, and so is the pop
        return own(list.pop, self, *args)
    item = handed(self, at, position(key), "pop")
    form = (
        ["[:]", self.expression, None, -1] if not args else dropped(self.expression, position(key))
    )
    made(self, lambda items: list.pop(items, at), form, frozenset())
    return item


def _pops(self: ListState, key: object, given: bool) -> bool:
    """The fork a pop records before Python may raise: not empty, or the index in range."""
    if given:
        return in_range(self, key, "pop")
    measured: Expression = ["!=", ["len", self.expression], 0]
    return forked(self.sink, measured, self.length() != 0, "pop", raising=True)


def remove(self: ListState, value: object, found: int | None) -> None:
    """``items.remove(x)`` once the search found ``x`` at ``found``, or raised: the list becomes
    ``items[:j] + items[j + 1:]``."""
    if found is None:
        # nothing is there to remove: Python's own refusal, from a list with nothing in it
        own(list.remove, [], value)
    else:
        form = joined(
            ["[:]", self.expression, None, found], ["[:]", self.expression, found + 1, None]
        )
        made(self, lambda items: list.__delitem__(items, found), form, frozenset())


def clear(self: ListState) -> None:
    """``items.clear()``: the list is ``[]``, a plain list, and nothing of the input is in it."""
    list.clear(self)
    fields = self.__dict__
    fields["shadow"] = []
    fields["expression"] = None


def reverse(self: ListState) -> None:
    """``items.reverse()``: the list becomes ``items[::-1]``."""
    if not self.holds("reverse"):
        own(list.reverse, self)
        return
    made(self, list.reverse, ["[:]", self.expression, None, None, -1], frozenset())


def repeat(self: ListState, count: Any, name: str) -> None:
    """``items *= k`` with a plain int ``k``: the list becomes ``items * k``."""
    change: Change = lambda items: list.__imul__(items, count)  # noqa: E731
    if plain_index(count) is None or not self.holds(name):
        unfollowed(self, name, change)
        return
    made(self, change, ["*", self.expression, plain_index(count)], frozenset())


def assign(self: ListState, key: Any, value: object) -> None:
    """``items[i] = x`` and ``items[a:b] = ys``.

    An index records its long-enough fork before Python may raise IndexError, and the list
    becomes ``items[:i] + [x] + items[i:][1:]``; a slice becomes
    ``items[:a] + ys + items[a:][len(items[a:b]):]``.
    """
    if isinstance(key, slice):
        _assign_slice(self, key, value)
        return
    change: Change = lambda items: list.__setitem__(items, key, value)  # noqa: E731
    form = written(value, "__setitem__")
    if form is UNWRITTEN or not follows(self, key) or not self.holds("__setitem__"):
        unfollowed(self, "__setitem__", change)
        return
    if not in_range(self, key, "__setitem__"):
        own(change, self)
    made(self, change, put(self.expression, position(key), form), frozenset({kind_of(value)}))


def _assign_slice(self: ListState, key: slice, value: object) -> None:
    taken, other = taken_in(value, "__setitem__")
    bounds = slice_bounds(key)
    change: Change = lambda items: list.__setitem__(items, key, taken)  # noqa: E731
    if bounds is None or other is None or not self.holds("__setitem__"):
        unfollowed(self, "__setitem__", change)
        return
    form, kinds = other
    made(self, change, spliced(self.expression, bounds, form), kinds)


def delete(self: ListState, key: Any) -> None:
    """``del items[i]`` and ``del items[a:b]``.

    An index records its long-enough fork before Python may raise IndexError, and the list
    becomes ``items[:i] + items[i:][1:]``; a slice becomes
    ``items[:a] + items[a:][len(items[a:b]):]``.
    """
    change: Change = lambda items: list.__delitem__(items, key)  # noqa: E731
    bounds = slice_bounds(key) if isinstance(key, slice) else None
    followed = bounds is not None or (not isinstance(key, slice) and follows(self, key))
    if not followed or not self.holds("__delitem__"):
        unfollowed(self, "__delitem__", change)
        return
    if bounds is not None:
        made(self, change, spliced(self.expression, bounds, None), frozenset())
        return
    if not in_range(self, key, "__delitem__"):
        own(change, self)
    made(self, change, dropped(self.expression, position(key)), frozenset())


def slice_bounds(key: slice) -> tuple[Expression, Expression] | None:
    """The bounds of a slice pyct follows as a change: a step of None or 1, each bound followed."""
    if key.step is not None and plain_index(key.step) != 1:
        return None
    ends = (key.start, key.stop)
    bounds = [None if end is None else position(end) for end in ends]
    if any(end is not None and bound is None for end, bound in zip(ends, bounds, strict=True)):
        return None
    return bounds[0], bounds[1]
