"""An object in the walk: whether its attributes are followed, which they are, and how its
copy takes a new value for one.

An object is followed once ``copy.deepcopy`` makes a new object of it, which is also the test
that it can be copied: a class, a function and an enum member copy as themselves, and a module
or an object holding a lock is refused, so each reaches the target as it came. A bound method
is copied and never followed.
"""

from __future__ import annotations

import types
from collections.abc import Iterator
from dataclasses import dataclass

from pyct.core.foundation.branch import Expression


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
    """Whether the walk follows what a value that is no int, float, str, bool or None holds,
    given a copy: a list's or a dict's items, a tuple's, any other object's attributes, and
    nothing of a bound method's."""
    return not isinstance(value, types.MethodType)


def attributes(value: object, made: object) -> Iterator[tuple[Attribute, object]]:
    """Each attribute both an object and its copy hold, with the object's value, in order: its
    ``__dict__``'s entries, then each slot its class and bases declare that is set."""
    fields, copied = _fields(value), _fields(made)
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

    None when the holder has no access, or the attribute's name is no identifier: no access
    written as Python would read it names the value there.
    """
    key = attribute.key
    if holder is None or not isinstance(key, str) or not key.isidentifier():
        return None
    return ["getattr", holder, str.__repr__(key)]


def _fields(value: object) -> dict[object, object] | None:
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
