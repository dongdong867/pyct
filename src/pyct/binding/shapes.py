"""What the solver knows of a tracked list in the input, and what it answers about one.

A list's shape is the kind of the item at each position of the input, the shape of each list
inside, and the kind of an item the solver adds (lists-and-dicts-as-arrays-with-a-length). An
answer is the list's new length, the arrays the solver chose its items from, and the positions
a fork on the path read, whose items take the solver's values; every other position keeps what
the input had.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

from pyct.binding.annotations import NONE, Check, Items, OneOf
from pyct.core.list_state import kind_of

# the kinds an added item takes from an annotation's item type, when the items do not say
_ANNOTATED: Mapping[type, str] = {int: "int", str: "str"}


@dataclass(frozen=True)
class ListShape:
    """A tracked list of the input: the kind at each position, the lists inside, and what the
    solver adds.

    ``rows`` holds the shape of each list inside by its position, each one the walk first
    reached there. ``fill`` is the kind of an added item, and ``fill_row`` the shape of an
    added list, which starts empty.
    """

    kinds: tuple[str, ...]
    rows: Mapping[int, ListShape] = field(default_factory=dict)
    fill: str = "none"
    fill_row: ListShape | None = None

    def runs(self) -> tuple[tuple[str, int, int], ...]:
        """The positions of the input in runs of one kind: each kind with where it starts and
        stops."""
        runs: list[tuple[str, int, int]] = []
        for at, kind in enumerate(self.kinds):
            if runs and runs[-1][0] == kind:
                runs[-1] = (kind, runs[-1][1], at + 1)
            else:
                runs.append((kind, at, at + 1))
        return tuple(runs)

    def kind_at(self, position: int) -> str:
        """The kind of the item at a position from the start: the input's, or an added one's."""
        return self.kinds[position] if position < len(self.kinds) else self.fill

    def row_at(self, position: int) -> ListShape | None:
        """The shape of the list at a position from the start, when one is there."""
        if position < len(self.kinds):
            return self.rows.get(position)
        return self.fill_row


def shaped(items: list[object], rows: Mapping[int, ListShape], check: Check | None) -> ListShape:
    """The shape of a list of the input, its lists inside already shaped.

    ``check`` is what the list's annotation asks of each item, when it has one.
    """
    kinds = tuple(kind_of(item) for item in items)
    fill = kinds[0] if kinds and kinds.count(kinds[0]) == len(kinds) else annotated(check)
    fill_row = empty(_each(check)) if fill == "list" else None
    return ListShape(kinds=kinds, rows=dict(rows), fill=fill, fill_row=fill_row)


def empty(check: Check | None) -> ListShape:
    """The shape of a list the solver adds: empty, its items taking the annotation's kind."""
    fill = annotated(check)
    return ListShape(kinds=(), fill=fill, fill_row=empty(_each(check)) if fill == "list" else None)


def annotated(check: Check | None) -> str:
    """The kind an annotation's item type gives an added item: an int, a str, either of them
    with None, a list, or a dict. Any other is `null`."""
    if isinstance(check, Items):
        return "list" if check.kind is list else "dict"
    if isinstance(check, type):
        return _ANNOTATED.get(check, "none")
    if isinstance(check, OneOf):
        kinds = [kind for kind in check.kinds if kind is not NONE]
        return _ANNOTATED.get(kinds[0], "none") if len(kinds) == 1 else "none"
    return "none"


def _each(check: Check | None) -> Check | None:
    """What a list annotation asks of each item of an item that is itself a list."""
    return check.each if isinstance(check, Items) and check.kind is list else None


@dataclass(frozen=True)
class ArrayValue:
    """One array the solver answered: a value at each position it stored, and one for the rest."""

    default: object
    stored: Mapping[int, object] = field(default_factory=dict)

    def at(self, position: int) -> object:
        return self.stored.get(position, self.default)


@dataclass(frozen=True)
class ListAnswer:
    """What the solver answered about one tracked list: its length, the arrays its items come
    from by kind, and the positions a fork on the path read."""

    length: int
    arrays: Mapping[str, ArrayValue] = field(default_factory=dict)
    read: frozenset[int] = frozenset()


# the item an added position holds when no array says, by its kind
_ADDED: Mapping[str, object] = {"int": 0, "str": ""}


def resized(items: list[object], answer: ListAnswer, shape: ListShape) -> list[object]:
    """The items of a list at its answered length.

    A position a fork read takes the solver's value; every other position of the input keeps
    its item, and an added one holds what the solver answers for its kind, or starts empty.
    """
    return [_item(items, answer, shape, at) for at in range(answer.length)]


def _item(items: list[object], answer: ListAnswer, shape: ListShape, at: int) -> object:
    kind = shape.kind_at(at)
    if at < len(items) and (at not in answer.read or kind not in _ADDED):
        return items[at]
    if kind in _ADDED:
        array = answer.arrays.get(kind)
        return _ADDED[kind] if array is None else array.at(at)
    return _STARTS[kind]() if kind in _STARTS else None


# an added list or dict starts empty
_STARTS: Mapping[str, Callable[[], object]] = {"list": list, "dict": dict}
