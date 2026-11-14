"""The values inside a list or a dict the walk places into its copy, each with the access one step
further in, and a dict's keys as an access and an annotation read them."""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum
from typing import Any, cast

from pyct.binding.annotations import Check, Fields, int_keys, item_check, reads_as_int
from pyct.binding.hints import Inside
from pyct.binding.seed_keys import ARGS_KEY, CLASS_KEY, read_key
from pyct.binding.tuples import Holder, Slot
from pyct.core.foundation.branch import Expression

# one value still to place: the value, its access, and where it goes. The access is None under
# a key no access can name
type Pending = tuple[object, Expression | None, Holder, Slot, Check | None]

# what the walk copies an object form and its "__args__" under: keys and length fixed
FIXED = Fields({})


def items_to_place(
    value: object,
    items: list[object] | dict[object, object],
    access: Expression | None,
    into: list[object] | dict[Any, object],
    check: Check | None,
) -> Iterable[Pending]:
    """A container's values to place into its copy, each with the access one step in.

    A list's and a dict's are the items the walk decided it takes. A dict's value is named by
    its key when the key can be written as a literal (see ``key_access``), and by nothing otherwise.
    It goes in under the copy's own key, in the same order: a copy deepcopy made holds copies
    of the seed's keys, and a key equal only to itself would go in twice. The copy's keys are
    read in C, since a tracked dict's own walk records forks. Each value takes what the
    container's check asks of it (``item_check``).
    """
    kind = list if isinstance(value, list) else dict
    if isinstance(items, list):
        return (
            (item, step(access, i), into, i, item_check(check, kind, i))
            for i, item in enumerate(items)
        )
    pairs = zip(dict.items(items), dict.keys(cast(dict[Any, object], into)), strict=True)
    return (
        (item, step(access, key_access(key)), into, slot, item_check(check, kind, key))
        for (key, item), slot in pairs
    )


def form_items(
    items: dict[object, object], access: Expression | None, into: dict[Any, object], ask: Inside
) -> Iterable[Pending]:
    """An object form's values to place into its copy, each under its own key.

    ``"__class__"`` goes under no access, so it is never tracked or named,
    and so does an ``"__args__"`` that is not a list. A list under
    ``"__args__"`` keeps its length, and its items are named by index, each
    taking the check of the constructor's parameter at its position. Every
    other value is named by its key and takes its parameter's check.
    """
    for key, item in dict.items(items):
        at = step(access, key_access(key))
        if _is(key, CLASS_KEY) or (_is(key, ARGS_KEY) and type(item) is not list):
            yield item, None, into, key, None
        elif _is(key, ARGS_KEY):
            yield item, at, into, key, ask.items
        else:
            yield item, at, into, key, ask.keys.each.get(key)


def _is(key: object, name: str) -> bool:
    """Whether a key is the str ``name``, with no ``__eq__`` of a key's own class run."""
    return type(key) is str and key == name


def keyed(value: dict[object, object], check: Check | None, *, plain: bool) -> dict[object, object]:
    """A dict's items, each key read back as its annotation's key type says, and a plain dict's
    escape read back too.

    JSON keys are always strings, so an int key an input's line wrote as ``"3"`` is read back
    as ``3`` under a ``dict[int, X]`` annotation, and the line's ``args`` given back through
    ``--args`` is the same input. A ``plain`` dict, exactly a ``dict`` that is no object form
    and not the dict under ``self``, reads ``"!__class__"`` back as ``"__class__"``
    (``seed_keys``). A key written any other way, or under any other annotation, stays as it
    came.
    """
    ints = int_keys(check)
    if not ints and not plain:
        return dict(value)
    return {_read_back(key, ints, plain): item for key, item in dict.items(value)}


def _read_back(key: object, ints: bool, plain: bool) -> object:
    """A key as the walk reads it: under a ``dict[int, X]`` the int an int's JSON text writes,
    in a plain dict an escaped key read back, else itself."""
    if ints and isinstance(key, str) and reads_as_int(key):
        return int(key)
    return read_key(key) if plain else key


class _Unnamed(Enum):
    """What ``key_access`` answers for a key no access can write, apart from every literal."""

    KEY = "a key no access can name"


def step(container: Expression | None, key: Expression | _Unnamed) -> Expression | None:
    """The access one step further in, ``["[]", container, key]``.

    None when the container has no access, or the key cannot be written.
    """
    if container is None or key is _Unnamed.KEY:
        return None
    return ["[]", container, key]


def key_access(key: object) -> Expression | _Unnamed:
    """A key as an access writes it: a str in its Python quotes, an int as itself.

    Any other key is ``_Unnamed.KEY``: no access names the value under it.
    The answer is apart from every literal, so a key written as ``null`` can
    join them later.
    """
    if isinstance(key, str):
        # str's own repr: a key of the target's own str subclass may print itself another way
        return str.__repr__(key)
    if isinstance(key, int) and not isinstance(key, bool):
        return int(key)
    return _Unnamed.KEY
