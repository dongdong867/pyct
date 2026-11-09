"""The deepcopy memo the walk copies through, and which copies one deepcopy of an object made
the walk may go into."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from pyct.binding import objects
from pyct.binding.tuples import buildable

# the types whose values hold nothing the walk follows
_ATOMIC: frozenset[type] = frozenset({int, float, str, bool, bytes, type(None)})


class Scratch(dict[int, Any]):
    """deepcopy's memo for one copy: what it copies now, read over what the walk already has.

    deepcopy looks a value up with ``get``, and a tuple's copy with an
    index, and records each copy by setting it. So this dict holds only the
    new copies, and the walk's stay as they were until the copy finishes. A
    look-up neither holds asks ``on_miss``, which may answer with a copy the
    walk makes then: a tuple it builds.
    """

    def __init__(
        self, under: Mapping[int, object], on_miss: Callable[[int], object | None] | None = None
    ) -> None:
        super().__init__()
        self._under = under
        self._on_miss = on_miss

    def get(self, key: int, default: Any = None) -> Any:
        if dict.__contains__(self, key):
            return dict.__getitem__(self, key)
        if key in self._under:
            return self._under[key]
        made = None if self._on_miss is None else self._on_miss(key)
        return default if made is None else made

    def __missing__(self, key: int) -> Any:
        return self._under[key]


def faithful_copies(value: object, memo: Mapping[int, object]) -> dict[int, object] | None:
    """The copies one deepcopy of a followed object made that the walk may go into, by the
    identity of each original; None when the object's own copy may not be gone into.

    Those are the object's own and each object the walk follows that it
    reaches through what the walk follows: a list's, a dict's or a tuple's
    items, a subclass of dict's or list's, and a followed object's
    attributes. Each must be followed and its copy faithful
    (``objects.faithful``), and nothing under a copy that is not is
    reached.
    """
    joined: dict[int, object] = {}
    seen: set[int] = set()
    stack = [value]
    while stack:
        each = stack.pop()
        if type(each) in _ATOMIC or id(each) in seen:
            continue
        seen.add(id(each))
        if type(each) is list or type(each) is dict or _rebuilt_tuple(each):
            stack.extend(_held(each))
            continue
        made = memo.get(id(each))
        if isinstance(each, tuple) or not objects.followed(each) or made is None:
            continue
        if objects.faithful(each, made, memo):
            joined[id(each)] = made
            stack.extend(_held(each))
    return joined if id(value) in joined else None


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
