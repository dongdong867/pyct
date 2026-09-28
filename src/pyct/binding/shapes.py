"""What the solver knows of a tracked list or dict in the input, and what it answers about one.

A list's shape is the kind of the item at each position of the input, the shape of each list
inside, and the kind of an item the solver adds (containers-arrays-counted-keys-and-copied-walk-
keys). An answer is the list's new length, the arrays the solver chose its items from, and the
positions a fork on the path read, whose items take the solver's values; every other position
keeps what the input had.

A dict's shape is its keys in order, the kind of each value, and the kind of a value the
solver adds. An answer is which keys a fork names the dict holds, how many of its other keys it
keeps, and how many keys pyct makes up to meet a count.
"""

from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass, field

from pyct.binding.annotations import NONE, Check, Items, OneOf, int_keys, reads_as_int
from pyct.core.list_state import kind_of

# the kinds an added item takes from an annotation's item type, when the items do not say
_ANNOTATED: Mapping[type, str] = {int: "int", str: "str", float: "float", bool: "bool"}


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
    """The kind an annotation's item type gives an added item, one the seed check accepts: a
    plain type's own, the first plain type a union names, a list, or a dict. An annotation the
    check reads nothing of gives `null`."""
    if isinstance(check, Items):
        return "list" if check.kind is list else "dict"
    if isinstance(check, type):
        return _ANNOTATED.get(check, "none")
    if isinstance(check, OneOf):
        kinds = [kind for kind in check.kinds if kind is not NONE]
        return _ANNOTATED.get(kinds[0], "none") if kinds else "none"
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


# the item an added position holds when no array says, by its kind: the solver answers an int
# or a str, and a float or a bool, which nothing solves yet, holds its type's own zero
_ADDED: Mapping[str, object] = {"int": 0, "str": "", "float": 0.0, "bool": False}


def resized(items: list[object], answer: ListAnswer, shape: ListShape) -> list[object]:
    """The items of a list at its answered length.

    A position a fork read takes the solver's value; every other position of the input keeps
    its item, and an added one holds what the solver answers for its kind, or starts empty.
    """
    return [_item(items, answer, shape, at) for at in range(answer.length)]


def _item(items: list[object], answer: ListAnswer, shape: ListShape, at: int) -> object:
    kind = shape.kind_at(at)
    array = answer.arrays.get(kind)
    if at < len(items) and (at not in answer.read or array is None):
        return items[at]
    if kind in _ADDED:
        return _ADDED[kind] if array is None else array.at(at)
    return _STARTS[kind]() if kind in _STARTS else None


# an added list or dict starts empty
_STARTS: Mapping[str, Callable[[], object]] = {"list": list, "dict": dict}


@dataclass(frozen=True)
class DictShape:
    """A tracked dict of the input: its keys in order, the kind of each value, and what the
    solver adds (dict-keys-named-held-or-made-up-by-key-type).

    ``fill`` is the kind of a value the solver adds under a key a fork names or one pyct makes
    up. ``int_keys`` says its annotation is ``dict[int, X]``, whose keys ``--args`` reads back as
    ints: an input's line writes a key as JSON text, so the solver adds an int key only there,
    and there no str key that reads as an int (see ``adds``). Such a dict whose keys are all
    ints gets made-up int keys, and any other dict whose keys are all strs made-up str keys
    (see ``made_up``).
    """

    keys: tuple[object, ...]
    kinds: tuple[str, ...]
    fill: str = "none"
    int_keys: bool = False

    @property
    def makes_up(self) -> bool:
        """Whether the solver may add made-up keys: the dict's keys are all of the type its
        made-up keys are."""
        return all(type(key) is self.made_type for key in self.keys)

    @property
    def made_type(self) -> type:
        """The type of the dict's made-up keys: int under ``dict[int, X]``, else str."""
        return int if self.int_keys else str

    def made_up(self, taken: Collection[object], count: int) -> list[object]:
        """The first ``count`` made-up keys, skipping any key in ``taken``: the keys the dict
        holds and the keys a fork names. An int-keyed dict's are the smallest non-negative
        ints, `0`, `1` and on; any other dict's `pyct1`, `pyct2` and on."""
        if not self.int_keys:
            return list(made_up(taken, count))
        ints = {key for key in taken if type(key) is int}
        keys: list[object] = []
        number = 0
        while len(keys) < count:
            if number not in ints:
                keys.append(number)
            number += 1
        return keys

    def adds(self, key: object) -> bool:
        """Whether the solver may add this key: one an answer's line reads back as itself
        through ``--args``."""
        if type(key) is int:
            return self.int_keys
        return type(key) is str and not (self.int_keys and reads_as_int(key))


def dict_shaped(items: dict[object, object], check: Check | None) -> DictShape:
    """The shape of a dict of the input. ``check`` is what the dict's own annotation asks of
    it, when it has one."""
    each = check.each if isinstance(check, Items) and check.kind is dict else None
    kinds = tuple(kind_of(value) for value in dict.values(items))
    fill = kinds[0] if kinds and kinds.count(kinds[0]) == len(kinds) else annotated(each)
    keys = tuple(dict.keys(items))
    return DictShape(keys=keys, kinds=kinds, fill=fill, int_keys=int_keys(check))


@dataclass(frozen=True)
class DictAnswer:
    """What the solver answered about one tracked dict.

    ``present`` says, for each key a fork on the path names, in the order the path first names
    it, whether the dict holds it. ``kept`` is how many of the input's other keys it keeps, from
    the first: a smaller dict loses them from its end. ``made`` is how many keys pyct makes up,
    and ``values`` what the solver answered for a value under an added key.
    """

    present: Mapping[object, bool] = field(default_factory=dict)
    kept: int = 0
    made: int = 0
    values: Mapping[object, object] = field(default_factory=dict)


# a made-up key is this, then a count from 1
MADE_UP = "pyct"


def made_up(taken: Collection[object], count: int) -> list[str]:
    """The first ``count`` made-up keys, `pyct1`, `pyct2` and on, skipping any text in
    ``taken``: the keys the dict holds and the keys a fork names."""
    keys: list[str] = []
    number = 0
    while len(keys) < count:
        number += 1
        key = f"{MADE_UP}{number}"
        if key not in taken:
            keys.append(key)
    return keys


def rekeyed(
    items: dict[object, object], answer: DictAnswer, shape: DictShape
) -> dict[object, object]:
    """The items of a dict with the keys the solver answered.

    The input's keys come first, in their order: one a fork names stays when the answer holds
    it, and the others stay as far as ``kept`` reaches. Then the added keys a fork names, in the
    order the path names them, and then the made-up keys. An added value holds what the solver
    answered, or its kind's own zero, or starts empty.
    """
    rebuilt: dict[object, object] = {}
    unnamed = 0
    for key, value in dict.items(items):
        if key in answer.present:
            keep = answer.present[key]
        else:
            keep, unnamed = unnamed < answer.kept, unnamed + 1
        if keep:
            rebuilt[key] = value
    added = [key for key, held in answer.present.items() if held and key not in items]
    added += shape.made_up({*items, *answer.present}, answer.made)
    for key in added:
        rebuilt[key] = answer.values.get(key, _filled(shape.fill))
    return rebuilt


def _filled(kind: str) -> object:
    """A value the solver adds and answers nothing about: its kind's zero, or an empty list or
    dict, or None."""
    if kind in _ADDED:
        return _ADDED[kind]
    return _STARTS[kind]() if kind in _STARTS else None
