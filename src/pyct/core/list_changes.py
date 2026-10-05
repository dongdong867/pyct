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

from pyct.core import spans
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
from pyct.core.spans import Span, exactly
from pyct.core.str_splits import a_split_s_list, built_from_a_split, kept_form
from pyct.core.values import own

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


def held(operands: tuple[object, ...]) -> list[tuple[Expression, int]]:
    """Each tracked int among the operands, a slice's bounds included, and the value it has."""
    found: list[tuple[Expression, int]] = []
    for operand in operands:
        parts = (
            (operand.start, operand.stop, operand.step)
            if isinstance(operand, slice)
            else (operand,)
        )
        found += [(part.expression, _number(part)) for part in parts if type(part) is ConcolicInt]
    return found


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


def made(
    self: ListState, change: Change, form: Expression, kinds: frozenset[str], span: Span
) -> object:
    """Make a change Python's own way, then on the shadow, and take on its form and the range
    that form holds."""
    answer = own(change, self)
    change(self.shadow)
    fields = self.__dict__
    fields["expression"] = kept_form(form)
    fields["kinds"] = self.kinds | kinds
    self.resized(span)
    return answer


def one_more(span: Span) -> Span:
    """The range once a change adds one item."""
    return spans.added(span, spans.exactly(1))


def one_less(span: Span) -> Span:
    """The range once a change takes one item out, which the list held."""
    fewest, most = span
    return (max((fewest or 0) - 1, 0), None if most is None else max(most - 1, 0))


def plain_bounds(bounds: tuple[Expression, Expression]) -> tuple[int | None, int | None] | None:
    """A slice's bounds as plain ints, a missing one None; None when either is tracked."""
    start, stop = bounds
    if (start is None or type(start) is int) and (stop is None or type(stop) is int):
        return start, stop
    return None


def unfollowed(self: ListState, name: str, change: Change) -> object:
    """A change pyct does not follow: Python makes it, and the list is plain from then on.

    A change that raises changes nothing, so it records nothing. The loss is named unless the
    list was plain already. A split's list leaves the split's machinery instead
    (``ListState.leave_the_split``): it names no loss, and its pieces stay tracked.
    """
    answer = own(change, self)
    if self.leave_the_split():
        return answer
    if self.expression is not None:
        self.lose(name)
    return plain(answer)


def added(value: list[object], name: str) -> tuple[Expression, frozenset[str]] | None:
    """The form and the kinds of a list another list takes in: its own form, or a display.

    None for a list that holds a value no expression holds. A tracked list whose form no longer
    holds is read as the plain list it is, named by ``name``.
    """
    if isinstance(value, ListState) and value.holds(name) and not a_split_s_list(value.expression):
        return value.expression, value.kinds
    # a split's list is taken in as origin/v2 takes in its plain list of pieces: a display
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
    kinds = frozenset({kind_of(value)})
    made(self, change, joined(self.expression, ["[,]", form]), kinds, one_more(self.span))


def extend(self: ListState, values: object, name: str = "extend") -> None:
    """``items.extend(ys)`` and ``items += ys``: the list becomes ``items + ys``.

    Python reads a non-list iterable once, so it is read into a list here and that list is
    what both the items and the form take in.
    """
    if isinstance(values, ListState) and takes_another(self, values):
        # as origin/v2's plain list of pieces takes in a tracked list: by Python's own walk
        self.leave_the_split()
        list.extend(self, values)
        return
    taken, other = taken_in(values, name)
    change: Change = lambda items: list.extend(items, taken)  # noqa: E731
    if other is None or not self.holds(name):
        unfollowed(self, name, change)
        return
    form, kinds = other
    span = spans.added(self.span, self.span_of(values if isinstance(values, list) else taken))
    made(self, change, joined(self.expression, form), kinds, span)


def takes_another(self: ListState, values: ListState) -> bool:
    """Whether a split's list takes in another tracked list that is not a split's list: on
    origin/v2, a plain list of pieces taking in a tracked list."""
    if not a_split_s_list(self.expression):
        return False
    return values.expression is not None and not built_from_a_split(values.expression)


def shown(self: ListState, name: str) -> None:
    """A split's list read from here on as origin/v2's plain list of pieces: a display of its
    pieces, each piece's form, or Python's own list where a display is not written."""
    form = displayed(list.copy(self), name)
    if form is UNWRITTEN:
        self.leave_the_split()
        return
    self.__dict__["expression"] = form
    self.resized(exactly(list.__len__(self)))


def insert(self: ListState, index: Any, value: object) -> None:
    """``items.insert(i, x)``: the list becomes ``items[:i] + [x] + items[i:]``.

    Insert clamps its position to the list, so it records no fork.
    """
    at, form = position(index), written(value, "insert")
    change: Change = lambda items: list.insert(items, index, value)  # noqa: E731
    if at is None or form is UNWRITTEN or not self.holds("insert"):
        unfollowed(self, "insert", change)
        return
    kinds = frozenset({kind_of(value)})
    made(self, change, placed(self.expression, at, form), kinds, one_more(self.span))


def pop(self: ListState, *args: Any) -> object:
    """``items.pop()`` and ``items.pop(i)``, handing out the item as indexed.

    ``pop()`` records that the list is not empty, and ``pop(i)`` the index's long-enough fork,
    each before Python may raise IndexError. The list becomes ``items[:-1]``, or
    ``items[:i] + items[i:][1:]``.
    """
    key = args[0] if args else -1
    if args and self.leave_the_split():
        # a split's list popped at a position is Python's own from the pop on, as on origin/v2
        return own(list.pop, self, *args)
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
    made(self, lambda items: list.pop(items, at), form, frozenset(), one_less(self.span))
    return item


def _pops(self: ListState, key: object, given: bool) -> bool:
    """The fork a pop records before Python may raise: not empty, or the index in range."""
    if given:
        return in_range(self, key, "pop")
    return self.measure("!=", 0, self.length() != 0, "pop", raising=True)


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
        change: Change = lambda items: list.__delitem__(items, found)  # noqa: E731
        made(self, change, form, frozenset(), one_less(self.span))


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
    made(self, list.reverse, ["[:]", self.expression, None, None, -1], frozenset(), self.span)


def repeat(self: ListState, count: Any, name: str) -> None:
    """``items *= k`` with a plain int ``k``: the list becomes ``items * k``."""
    change: Change = lambda items: list.__imul__(items, count)  # noqa: E731
    if plain_index(count) is None or not self.holds(name):
        unfollowed(self, name, change)
        return
    times = plain_index(count)
    assert times is not None
    made(self, change, ["*", self.expression, times], frozenset(), spans.repeated(self.span, times))


def assign(self: ListState, key: Any, value: object) -> None:
    """``items[i] = x`` and ``items[a:b] = ys``.

    An index records its long-enough fork before Python may raise IndexError, and the list
    becomes ``items[:i] + [x] + items[i:][1:]``; a slice becomes
    ``items[:a] + ys + items[a:][len(items[a:b]):]``.
    """
    if self.leave_the_split():
        # a split's list set at a position is Python's own from the set on, as on origin/v2
        own(list.__setitem__, self, key, value)
        return
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
    kinds = frozenset({kind_of(value)})
    made(self, change, put(self.expression, position(key), form), kinds, self.span)


def _assign_slice(self: ListState, key: slice, value: object) -> None:
    taken, other = taken_in(value, "__setitem__")
    bounds = slice_bounds(key)
    change: Change = lambda items: list.__setitem__(items, key, taken)  # noqa: E731
    if bounds is None or other is None or not self.holds("__setitem__"):
        unfollowed(self, "__setitem__", change)
        return
    form, kinds = other
    span = spans.added(
        _cut(self, bounds), self.span_of(value if isinstance(value, list) else taken)
    )
    made(self, change, spliced(self.expression, bounds, form), kinds, span)


def delete(self: ListState, key: Any) -> None:
    """``del items[i]`` and ``del items[a:b]``.

    An index records its long-enough fork before Python may raise IndexError, and the list
    becomes ``items[:i] + items[i:][1:]``; a slice becomes
    ``items[:a] + items[a:][len(items[a:b]):]``.
    """
    change: Change = lambda items: list.__delitem__(items, key)  # noqa: E731
    if self.leave_the_split():
        # a split's list deleted from is Python's own from the delete on, as on origin/v2
        own(change, self)
        return
    bounds = slice_bounds(key) if isinstance(key, slice) else None
    followed = bounds is not None or (not isinstance(key, slice) and follows(self, key))
    if not followed or not self.holds("__delitem__"):
        unfollowed(self, "__delitem__", change)
        return
    if bounds is not None:
        made(self, change, spliced(self.expression, bounds, None), frozenset(), _cut(self, bounds))
        return
    if not in_range(self, key, "__delitem__"):
        own(change, self)
    made(self, change, dropped(self.expression, position(key)), frozenset(), one_less(self.span))


def _cut(self: ListState, bounds: tuple[Expression, Expression]) -> Span:
    """The range left once a slice is cut out. A tracked bound may cut another number of items
    on another input that takes the path, with no fork to say so, so it marks the list."""
    plain = plain_bounds(bounds)
    if plain is None:
        self.mark()
        return self.span
    return spans.cut_out(self.span, *plain)


def slice_bounds(key: slice) -> tuple[Expression, Expression] | None:
    """The bounds of a slice pyct follows as a change: a step of None or 1, each bound followed."""
    if key.step is not None and plain_index(key.step) != 1:
        return None
    ends = (key.start, key.stop)
    bounds = [None if end is None else position(end) for end in ends]
    if any(end is not None and bound is None for end, bound in zip(ends, bounds, strict=True)):
        return None
    return bounds[0], bounds[1]
