"""The deepcopy memo the walk copies through, and which copies one deepcopy of an object made
the walk may go into."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pyct.binding import objects
from pyct.binding.tuples import buildable


class Scratch(dict[int, Any]):
    """deepcopy's memo for one copy: what it copies now, read over another memo.

    deepcopy looks a value up with ``get``, and a tuple's copy with an
    index, and records each copy by setting it. So this dict holds only the
    new copies, and the memo under it stays as it was; the caller adds what
    it takes of them once the copy finishes.
    """

    def __init__(self, under: Mapping[int, object]) -> None:
        super().__init__()
        self._under = under

    def get(self, key: int, default: Any = None) -> Any:
        if dict.__contains__(self, key):
            return dict.__getitem__(self, key)
        return self._under.get(key, default)

    def __missing__(self, key: int) -> Any:
        return self._under[key]


@dataclass(frozen=True)
class Joined:
    """The copies one deepcopy of an object made that the walk may go into, by the identity
    of each original, and for each the original keys of a dict subclass in the order its copy
    holds them, empty for any other value."""

    copies: dict[int, object]
    keys: dict[int, list[object]]


def faithful_copies(value: object, memo: Scratch) -> Joined | None:
    """The copies one deepcopy of a followed object made that the walk may go into; None when
    the object's own copy may not be gone into.

    Each is a copy in this deepcopy's own memo, of an object the walk
    follows, and faithful (``objects.faithful``), reached from the object
    through what the walk follows in the copies this deepcopy made: a
    list's, a dict's or a tuple's items, a subclass of dict's or list's, and
    a followed object's attributes. The walk's earlier copies are neither
    judged again nor gone through.
    """
    joined = Joined({}, {})
    seen: set[int] = set()
    stack = [value]
    while stack:
        each = stack.pop()
        if id(each) in seen or not dict.__contains__(memo, id(each)):
            continue
        seen.add(id(each))
        made = dict.__getitem__(memo, id(each))
        if type(each) is list or type(each) is dict or _rebuilt_tuple(each):
            stack.extend(_held(each))
        elif objects.followed(each):
            keys = objects.faithful(each, made, memo)
            if keys is not None:
                joined.copies[id(each)] = made
                joined.keys[id(each)] = keys
                stack.extend(_held(each))
    return joined if id(value) in joined.copies else None


def _rebuilt_tuple(value: object) -> bool:
    """Whether a value is a tuple the walk builds from its items."""
    return isinstance(value, tuple) and buildable(value)


def _held(value: object) -> list[object]:
    """What the walk follows inside a value: a dict's values, a list's or a tuple's items, or
    an object's attributes."""
    if isinstance(value, dict):
        return list(dict.values(value))
    if isinstance(value, list):
        return list(list.__iter__(value))
    if isinstance(value, tuple):
        return list(tuple.__iter__(value))
    return [item for _, item in objects.attributes(value, value).pairs]
