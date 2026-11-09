"""An object in the walk: whether its attributes are followed, which they are, and how its
copy takes a new value for one.

An object is followed when no class on its MRO writes one of the copy, pickling or look-up
methods the copy rule names in Python, and its exact class has no ``copyreg`` reducer
(``copies_by_default``); when its own ``__dict__`` holds none of those names, and it holds an
attribute or is a subclass of dict or list (``followed``); and when ``copy.deepcopy`` makes a
faithful copy of it (``faithful``), which is also the test that it can be copied: a module or
an object holding a lock is refused, and reaches the target as it came. A class, a function, an
enum member and a bound method are never followed.
"""

from __future__ import annotations

import copyreg
import keyword
import types
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import cast

from pyct.core.foundation.branch import Expression

# the names this rule refuses a class for defining in Python, or an instance for holding in its
# own __dict__: the copy and pickling methods deepcopy's route calls, and the two that can
# answer its look-up of one
_HOOKS = (
    "__deepcopy__",
    "__reduce__",
    "__reduce_ex__",
    "__getstate__",
    "__setstate__",
    "__new__",
    "__getnewargs__",
    "__getnewargs_ex__",
    "__getattr__",
    "__getattribute__",
)

# what a hook built into Python is: object's own, or a builtin or extension type's
_BUILT_IN = (
    types.BuiltinFunctionType,
    types.MethodDescriptorType,
    types.WrapperDescriptorType,
    types.ClassMethodDescriptorType,
)


@dataclass(frozen=True, eq=False)
class Held:
    """An object's copy, as the holder the walk writes its attributes into."""

    made: object


@dataclass(frozen=True)
class Attributes:
    """What an object takes from the walk: each attribute it and its copy both hold, with the
    object's value, in order."""

    pairs: tuple[tuple[Attribute, object], ...]


@dataclass(frozen=True)
class Attribute:
    """Where an object keeps one attribute: in its ``__dict__`` under ``key``, or in the slot
    ``slot`` its class declares under that name.

    A value is written there directly, never through the class's ``__setattr__``, so a frozen
    dataclass takes it as its own ``__init__`` stores it.
    """

    key: object
    slot: types.MemberDescriptorType | None = None

    def write(self, into: object, value: object) -> None:
        """Put ``value`` in ``into``'s copy of this attribute."""
        if self.slot is None:
            dict.__setitem__(object.__getattribute__(into, "__dict__"), self.key, value)
        else:
            self.slot.__set__(into, value)


def followed(value: object) -> bool:
    """Whether the walk follows what a value that is no tuple, and no plain dict or list, holds:
    a subclass of dict's or list's items, or an object's attributes, when its class passes
    ``copies_by_default`` and its own ``__dict__`` holds none of the names that rule reads. A
    bound method holds nothing the walk follows."""
    if isinstance(value, types.MethodType) or not copies_by_default(type(value)):
        return False
    fields = own_fields(value)
    if fields is not None and any(dict.__contains__(fields, name) for name in _HOOKS):
        return False
    return isinstance(value, list | dict) or any(True for _ in _pairs(value, value))


def copies_by_default(cls: type) -> bool:
    """Whether no class on a class's MRO defines ``__deepcopy__``, ``__reduce__``,
    ``__reduce_ex__``, ``__getstate__``, ``__setstate__``, ``__new__``, ``__getnewargs__``,
    ``__getnewargs_ex__``, ``__getattr__`` or ``__getattribute__`` in Python code, a method
    built into Python passing, and the class itself has no reducer in
    ``copyreg.dispatch_table``."""
    if cls in copyreg.dispatch_table:
        return False
    for each in cls.__mro__:
        for name in _HOOKS:
            hook = each.__dict__.get(name)
            if hook is not None and not isinstance(hook, _BUILT_IN):
                return False
    return True


def faithful(value: object, made: object, memo: Mapping[int, object]) -> list[object] | None:
    """The original dict subclass's keys in the order its copy holds them, or an empty list for
    any other value, when a deepcopy is a new object of the original's type and shape: a list
    subclass's length, and a dict subclass's keys and its ``__dict__``'s, each copied key the
    one deepcopy made of an original key (``keys_as_copied``); None when it is not."""
    if made is value or type(made) is not type(value):
        return None
    # the copy is of the value's own type, so a list's copy is a list and a dict's a dict
    if isinstance(value, list) and list.__len__(cast(list[object], made)) != list.__len__(value):
        return None
    keys = (
        keys_as_copied(value, cast(dict[object, object], made), memo)
        if isinstance(value, dict)
        else []
    )
    fields, copied = own_fields(value), own_fields(made)
    if keys is None or (fields is None) != (copied is None):
        return None
    if fields is None or copied is None or keys_as_copied(fields, copied, memo) is not None:
        return keys
    return None


def keys_as_copied(
    value: dict[object, object], made: dict[object, object], memo: Mapping[int, object]
) -> list[object] | None:
    """The original dict's keys in the order its copy holds them, when each copied key is the
    one deepcopy made of an original key and each original key has one; None otherwise.

    Both dicts are read with ``dict``'s own methods, so no subclass's code
    runs, and no key's ``__eq__``. ``memo`` is that deepcopy's: a key it
    made is found there under the original's identity, and one it copies
    as itself is the original.
    """
    original = {id(memo.get(id(key), key)): key for key in dict.keys(value)}
    if len(original) != dict.__len__(value) or dict.__len__(made) != len(original):
        return None
    order = [original.get(id(key), _MISSING) for key in dict.keys(made)]
    return None if any(key is _MISSING for key in order) else order


# what ``keys_as_copied`` finds for a copied key no original key has
_MISSING = object()


def attributes(value: object, made: object) -> Attributes:
    """What an object takes from the walk, given its copy of the same type."""
    return Attributes(tuple(_pairs(value, made)))


def _pairs(value: object, made: object) -> Iterator[tuple[Attribute, object]]:
    """Each attribute both an object and its copy hold, with the object's value, in order: its
    ``__dict__``'s entries, then each slot its class and bases declare that is set."""
    fields, copied = own_fields(value), own_fields(made)
    if fields is not None and copied is not None:
        for key, item in dict.items(fields):
            if dict.__contains__(copied, key):
                yield Attribute(key), item
    for name, slot in _slots(type(value)):
        if fields is not None and dict.__contains__(fields, name):
            continue
        try:
            item = slot.__get__(value, type(value))
            slot.__get__(made, type(made))
        except AttributeError:
            continue
        yield Attribute(name, slot), item


def step(holder: Expression | None, attribute: Attribute) -> Expression | None:
    """The access to an attribute, ``["getattr", holder, "'<name>'"]``.

    None when the holder has no access, or the attribute's name is no identifier or is a
    keyword: no access written as Python would read it names the value there.
    """
    key = attribute.key
    if holder is None or not isinstance(key, str) or not key.isidentifier():
        return None
    if keyword.iskeyword(key):
        return None
    return ["getattr", holder, str.__repr__(key)]


def own_fields(value: object) -> dict[object, object] | None:
    """An object's own ``__dict__``, read past any ``__getattribute__`` of its class; None for
    an object with none."""
    try:
        fields = object.__getattribute__(value, "__dict__")
    except AttributeError:
        return None
    return fields if isinstance(fields, dict) else None


def _slots(cls: type) -> Iterator[tuple[str, types.MemberDescriptorType]]:
    """Each slot a class and its bases declare, by the name it is stored under, the class's
    own first: a private name such as ``__key`` is stored mangled, ``_Class__key``."""
    seen: set[str] = set()
    for each in cls.__mro__:
        declared = each.__dict__.get("__slots__", ())
        for name in (declared,) if isinstance(declared, str) else declared:
            stored = _mangled(each, name)
            slot = each.__dict__.get(stored)
            if isinstance(slot, types.MemberDescriptorType) and stored not in seen:
                seen.add(stored)
                yield stored, slot


def _mangled(cls: type, name: str) -> str:
    """A name as Python stores it when the class body declares it: a private name mangled."""
    owner = cls.__name__.lstrip("_")
    if name.startswith("__") and not name.endswith("__") and owner:
        return f"_{owner}{name}"
    return name
