"""An object in the walk: whether its attributes are followed, which they are, and how its
copy takes a new value for one.

An object is followed when its class copies by Python's default route and it holds an
attribute, or is a subclass of dict or list, and then once ``copy.deepcopy`` makes a new object
of it of the same type, which is also the test that it can be copied: a module or an object
holding a lock is refused, and reaches the target as it came. A class, a function, an enum
member and a bound method are never followed.
"""

from __future__ import annotations

import keyword
import types
from collections.abc import Iterator
from dataclasses import dataclass

from pyct.core.foundation.branch import Expression

# the methods a class may copy itself by, in place of Python's default route
_HOOKS = ("__deepcopy__", "__copy__", "__reduce__", "__reduce_ex__", "__getstate__", "__setstate__")

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
    a subclass of dict's or list's items, or an object's attributes, when its class copies by
    Python's default route. A bound method holds nothing the walk follows."""
    if isinstance(value, types.MethodType) or not copies_by_default(type(value)):
        return False
    return isinstance(value, list | dict) or any(True for _ in _pairs(value, value))


def copies_by_default(cls: type) -> bool:
    """Whether deepcopy copies an instance of a class by Python's default route: no class on
    its MRO defines a copy or pickling hook in Python code. A hook built into Python, object's
    own or a builtin or extension type's, is that route; one written in Python may give back a
    copy of any shape, or another object altogether, so what it makes is handed on as made."""
    for each in cls.__mro__:
        for name in _HOOKS:
            hook = each.__dict__.get(name)
            if hook is not None and not isinstance(hook, _BUILT_IN):
                return False
    return True


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
