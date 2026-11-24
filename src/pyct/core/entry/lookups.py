"""An index read the target writes, ``x[k]``, which `pyct.intercept` hands here as
``__pyct_item__(x, k)``, and a plain dict's own ``get``, which `pyct.core.entry.watch` hands
back as a router.

A tracked key into a plain dict forks on which key the lookup finds: one `==` fork per key, in
the dict's order, until one holds, as `in` on a dict searches (`pyct.core.entry.hashed`), up to
`LOOKED_UP_MOST` keys. Every other read is Python's own.

`item` and `_Get.__call__` are routers: they run Python's own read, and none of the target's
code in their own lines, so blame reads through their frames (`PASSING`): a raise under
one, from Python's read or from the target's own `__getitem__`, is the target's.
"""

from __future__ import annotations

import types
from typing import TypeGuard, cast

from pyct.core.entry.hashed import HASHABLE, NOT_FOUND, element_pairs, found

# the most keys a lookup compares one by one; past it Python answers
LOOKED_UP_MOST = 300

# what `_search` answers for a dict it does not search
_UNSEARCHED = object()
# the type of a builtin function or method, as `{}.get` is
_BUILTIN = type({}.get)
_dict_get, _dict_getitem = dict.get, dict.__getitem__


def item(container: object, key: object) -> object:
    """``container[key]``, as Python reads it, a tracked key into a plain dict forking on the key
    it finds."""
    if type(key) in HASHABLE and _plain_dict(container):
        element = _search(container, key)
        if element is not NOT_FOUND and element is not _UNSEARCHED:
            return _dict_getitem(container, element)
    return container[key]  # pyrefly: ignore[bad-index]


class _Get:
    """A plain dict's own ``get``, read as a lookup when its key is tracked."""

    __slots__ = ("bound", "container")

    def __init__(self, bound: types.BuiltinMethodType, container: dict[object, object]) -> None:
        self.bound = bound
        self.container = container

    def __call__(self, *args: object, **kwargs: object) -> object:
        if kwargs or not 1 <= len(args) <= 2 or type(args[0]) not in HASHABLE:
            return self.bound(*args, **kwargs)
        element = _search(self.container, args[0])
        if element is _UNSEARCHED:
            return self.bound(*args)
        if element is NOT_FOUND:
            return args[1] if len(args) == 2 else None
        return _dict_getitem(self.container, element)


def routed[Callee](callee: Callee) -> Callee:
    """The callee, or the router that reads a plain dict's own ``get`` as a lookup."""
    if type(callee) is _BUILTIN and callee.__name__ == "get":  # pyrefly: ignore[missing-attribute]
        holder = callee.__self__  # pyrefly: ignore[missing-attribute]
        if _plain_dict(holder):
            return cast(Callee, _Get(callee, holder))  # pyrefly: ignore[bad-argument-type]
    return callee


def _plain_dict(container: object) -> TypeGuard[dict[object, object]]:
    """Whether the container is a dict whose type keeps dict's own ``get`` and ``__getitem__``."""
    if not isinstance(container, dict):
        return False
    kind = type(container)
    return kind.get is _dict_get and kind.__getitem__ is _dict_getitem


def _search(container: dict[object, object], key: object) -> object:
    """The dict's own key the tracked key finds, `NOT_FOUND`, or `_UNSEARCHED` for a dict past
    `LOOKED_UP_MOST` or one with a key pyct does not compare. The base type's own length and
    order are read, so a subclass's `__len__` or `__iter__` never runs where Python's lookup would
    not run it."""
    if dict.__len__(container) > LOOKED_UP_MOST:
        return _UNSEARCHED
    pairs = element_pairs(dict.__iter__(container))
    if pairs is None:
        return _UNSEARCHED
    return found(key, pairs)  # pyrefly: ignore[bad-argument-type]


# the frames blame reads through
PASSING: frozenset[types.CodeType] = frozenset({item.__code__, _Get.__call__.__code__})
