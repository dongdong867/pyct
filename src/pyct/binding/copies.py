"""The deepcopy memo the walk copies through, and which copies one deepcopy of an object made
the walk may go into."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pyct.binding import objects
from pyct.binding.tuples import buildable


class Scratch(dict[int, Any]):
    """deepcopy's memo for one copy: what it copies now, read over what the walk already has.

    deepcopy looks a value up with ``get``, and a tuple's copy with an
    index, and records each copy by setting it. So this dict holds only the
    new copies, and those under it, the walk's or another copy's under way,
    stay as they were until this copy finishes. A look-up none holds asks
    ``on_miss``, which may answer with a copy the walk makes then: a tuple
    it builds.
    """

    def __init__(
        self, under: Mapping[int, object], on_miss: Callable[[int], object | None] | None = None
    ) -> None:
        super().__init__()
        self._under = under
        self._on_miss = on_miss

    def find(self, key: int) -> object:
        """The copy this memo, or one under it, holds for an original, or ``MISSING``."""
        if dict.__contains__(self, key):
            return dict.__getitem__(self, key)
        if isinstance(self._under, Scratch):
            return self._under.find(key)
        return self._under.get(key, MISSING)

    def get(self, key: int, default: Any = None) -> Any:
        found = self.find(key)
        if found is MISSING and self._on_miss is not None:
            found = self._on_miss(key)
            found = MISSING if found is None else found
        return default if found is MISSING else found

    def __missing__(self, key: int) -> Any:
        found = self.find(key)
        if found is MISSING:
            raise KeyError(key)
        return found


# what ``Scratch.find`` answers for an original no memo holds a copy of
MISSING = object()


@dataclass(frozen=True)
class Joined:
    """The copies one deepcopy of an object made that the walk may go into, by the identity
    of each original, and the original keys of each dict subclass among them in the order its
    copy holds them."""

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
        elif objects.followed(each) and objects.faithful(each, made, memo):
            joined.copies[id(each)] = made
            if isinstance(each, dict) and isinstance(made, dict):
                joined.keys[id(each)] = objects.keys_as_copied(each, made, memo) or []
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
