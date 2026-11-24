"""An index read the target writes, ``x[k]``, which `pyct.intercept` hands here as
``__pyct_item__(x, k)``, and a plain dict's own ``get``, which `pyct.core.entry.watch` hands
back as a router.

A tracked key into a plain dict forks on which key the lookup finds: one `==` fork per key, in
the dict's order, until one holds, as `in` on a dict searches (`pyct.core.entry.hashed`), up to
`LOOKED_UP_MOST` keys. A tracked int or bool into a plain list or tuple forks on `n >= 0` and then
on `n == i` for each position, or `n == -i` counted from the end, up to `LOOKED_UP_MOST` items,
and into a plain str reads the str as a tracked str made from its text. Every other read is
Python's own.

`item` and `_Get.__call__` are routers: they run Python's own read, and none of the target's
code in their own lines, so blame reads through their frames (`PASSING`): a raise under
one, from Python's read or from the target's own `__getitem__`, is the target's.
"""

from __future__ import annotations

import types
from typing import TypeGuard, cast

from pyct.core.entry.hashed import HASHABLE, NOT_FOUND, Tracked, element_pairs, found
from pyct.core.foundation.branch import Downgrade, caller_site
from pyct.core.foundation.escapes import lost
from pyct.core.foundation.values import own
from pyct.core.numbers.bools import ConcolicBool
from pyct.core.numbers.ints import ConcolicInt
from pyct.core.strs.str_operands import literal
from pyct.core.strs.strs import ConcolicStr

# the most keys a lookup compares one by one; past it Python answers
LOOKED_UP_MOST = 300

# the tracked values that index a list, a tuple or a str
_POSITIONS = (ConcolicInt, ConcolicBool)
# what `_search` answers for a dict it does not search
_UNSEARCHED = object()
# the type of a builtin function or method, as `{}.get` is
_BUILTIN = type({}.get)
_dict_get, _dict_getitem = dict.get, dict.__getitem__


def item(container: object, key: object) -> object:
    """``container[key]``, as Python reads it, a tracked key into a plain dict forking on the key
    it finds, and a tracked int into a plain list, tuple or str forking on the item it picks."""
    if type(key) in HASHABLE and _plain_dict(container):
        element = _search(container, key)
        if element is _UNSEARCHED:
            return _unsearched(container, key, "__getitem__")
        if element is not NOT_FOUND:
            return _dict_getitem(container, element)
    elif type(key) in _POSITIONS:
        if type(container) is str:
            return _character(container, cast(ConcolicInt, key))
        if type(container) is list or type(container) is tuple:
            if len(container) > LOOKED_UP_MOST:
                return _unsearched(container, key, "__getitem__")
            at = _position(container, cast(ConcolicInt, key))
            if at is not None:
                return container[at]
    return container[key]  # pyrefly: ignore[bad-index]


def _unsearched(container: object, key: object, name: str) -> object:
    """``container[key]`` as Python reads it, then a downgrade named for the read: the lookup is
    one pyct does not follow. A read that raises records nothing."""
    answer = container[key]  # pyrefly: ignore[bad-index]
    lost(cast(Tracked, key).sink, Downgrade(name=name, site=caller_site()))
    return answer


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
            answer = self.bound(*args)
            lost(cast(Tracked, args[0]).sink, Downgrade(name="get", site=caller_site()))
            return answer
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


def _position(container: list[object] | tuple[object, ...], key: ConcolicInt) -> int | None:
    """The position the tracked int picks, as `n == i` for each position from the start, or
    `n == -i` from the end, once `n >= 0` is decided; None for an empty container, one past
    `LOOKED_UP_MOST`, or a position none holds, which Python's own read raises for."""
    size = len(container)
    if not 0 < size <= LOOKED_UP_MOST:
        return None
    for at in range(size) if key >= 0 else range(-1, -size - 1, -1):
        if key == at:
            return at
    return None


def _character(text: str, key: ConcolicInt) -> object:
    """``text[key]``: a tracked str made from the text, indexed as a tracked str is, or str's own
    read and a downgrade named `__getitem__` for a text holding a character past the last one
    cvc5 holds."""
    form = literal(text, ConcolicStr)
    if form is None:
        answer = own(str.__getitem__, text, key)
        lost(key.sink, Downgrade(name="__getitem__", site=caller_site()))
        return answer
    return ConcolicStr.made(text, expression=form, sink=key.sink)[key]


# the frames blame reads through
PASSING: frozenset[types.CodeType] = frozenset({item.__code__, _Get.__call__.__code__})
