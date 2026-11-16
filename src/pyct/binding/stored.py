"""A field an instance stores itself, read so that none of its class's code runs, and whether its
value is plain data.

An instance stores a field in its own ``__dict__`` or in a slot. Any other
name its class answers, through a property, a descriptor, ``__getattr__``,
an own ``__getattribute__`` or a ``__dict__`` property, runs the class's
code to answer, so it is never read. Every namespace is read through
``type``'s own descriptors, each key matched by walking the namespace's items
and comparing only a key that is exactly a ``str``, and each type compared by
identity, so no hook of the class, its metaclass or a key's runs.

A value is plain data when it is exactly a ``None``, bool, int, float or
str, plain or as pyct tracks it, or a list, tuple or dict of those at any
depth: each operation on it is Python's own or pyct's.
"""

from __future__ import annotations

import types
from collections.abc import Iterable
from typing import cast

from pyct.binding.classes import mro_of, namespace_of
from pyct.core.dicts.dicts import ConcolicDict
from pyct.core.lists.lists import ConcolicList
from pyct.core.numbers.bools import ConcolicBool
from pyct.core.numbers.floats import ConcolicFloat
from pyct.core.numbers.ints import ConcolicInt
from pyct.core.strs.strs import ConcolicStr

# why a field is not read: the class answers the name with code of its own, the instance stores
# no such field, or the field's value is not plain data
BY_CODE = "the class reads it with code"
ABSENT = "the object holds no such field"
AN_OBJECT = "it holds an object"

# the types of a plain value that holds no other, plain or tracked, each compared by identity
_SCALARS: tuple[type, ...] = (
    type(None),
    bool,
    int,
    float,
    str,
    ConcolicBool,
    ConcolicInt,
    ConcolicFloat,
    ConcolicStr,
)
# what Python's own attribute read is, which reads an instance's fields and its class's names
_OWN_READ = vars(object)["__getattribute__"]
# a name no namespace holds
_NOWHERE = object()


class FieldUnreadError(Exception):
    """A field pyct does not read: ``reason`` says which, and why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def read_field(owner: object, name: str, field: str) -> object:
    """The field ``field`` of ``owner``, the parameter ``name`` holds, as the instance stores it,
    when its value is plain data. A ``FieldUnreadError`` says why it is not read."""
    found = _stored(owner, field)
    if isinstance(found, _Why):
        raise FieldUnreadError(f"it cannot read {name}.{field}: {found.reason}")
    if not plain_data(found):
        raise FieldUnreadError(f"it cannot read {name}.{field}: {AN_OBJECT}")
    return found


class _Why:
    """Why ``_stored`` read no field."""

    def __init__(self, reason: str) -> None:
        self.reason = reason


def _stored(owner: object, field: str) -> object:
    """What the instance stores under ``field``, in a slot or its own ``__dict__``, or ``_Why``
    it reads none. Python reads a slot or any other data descriptor before the instance's
    ``__dict__``, so a data descriptor other than a slot is the class's code."""
    cls = type(owner)
    mro = mro_of(cls)
    if _class_name(mro, "__getattribute__") is not _OWN_READ:
        return _Why(BY_CODE)
    held = _class_name(mro, field)
    if type(held) is types.MemberDescriptorType:
        return _slot(cast(types.MemberDescriptorType, held), owner, cls)
    if held is not _NOWHERE and _data_descriptor(type(held)):
        return _Why(BY_CODE)
    holder = _class_name(mro, "__dict__")
    if holder is _NOWHERE:
        return _Why(ABSENT)
    if type(holder) is not types.GetSetDescriptorType:
        return _Why(BY_CODE)
    fields = _own_dict(cast(types.GetSetDescriptorType, holder), owner, cls)
    if type(fields) is not dict:
        return _Why(BY_CODE)
    found = _matching(dict.items(cast(dict[object, object], fields)), field)
    return _Why(ABSENT) if found is _NOWHERE else found


def _slot(held: types.MemberDescriptorType, owner: object, cls: type) -> object:
    """What a slot holds, read by Python's own C code, or ``_Why`` when it holds nothing or is
    another class's slot, which reads no instance of this one."""
    try:
        return held.__get__(owner, cls)
    except AttributeError:
        return _Why(ABSENT)
    except TypeError:
        return _Why(BY_CODE)


def _own_dict(holder: types.GetSetDescriptorType, owner: object, cls: type) -> object:
    """The instance's ``__dict__``, read by Python's own C code, or ``_Why`` when the getter is
    another class's, which reads no instance of this one."""
    try:
        return holder.__get__(owner, cls)
    except TypeError:
        return _Why(BY_CODE)


def _data_descriptor(kind: type) -> bool:
    """Whether a class attribute of type ``kind`` answers a read before the instance's
    ``__dict__``: its type defines ``__get__`` and ``__set__`` or ``__delete__``."""
    mro = mro_of(kind)
    reads = _class_name(mro, "__get__") is not _NOWHERE
    writes = any(_class_name(mro, name) is not _NOWHERE for name in ("__set__", "__delete__"))
    return reads and writes


def _class_name(mro: tuple[type, ...], name: str) -> object:
    """The first value a namespace of ``mro`` holds under ``name``, or ``_NOWHERE``."""
    for each in mro:
        space = cast(types.MappingProxyType[object, object], namespace_of(each))
        found = _matching(types.MappingProxyType.items(space), name)
        if found is not _NOWHERE:
            return found
    return _NOWHERE


def _matching(items: Iterable[tuple[object, object]], name: str) -> object:
    """The value under the key that is exactly the str ``name``, or ``_NOWHERE``: walked, not
    looked up, since a lookup compares a key of the same hash with that key's own ``__eq__``."""
    for key, value in items:
        if type(key) is str and str.__eq__(cast(str, key), name):
            return value
    return _NOWHERE


def plain_data(value: object) -> bool:
    """Whether ``value`` is plain data, as the module says. Read in a loop, each list, tuple and
    dict once, through their own types' iteration, so no subclass's code runs."""
    pending = [value]
    seen: set[int] = set()
    while pending:
        each = pending.pop()
        kind = type(each)
        if any(kind is scalar for scalar in _SCALARS):
            continue
        held = _held(each, kind)
        if held is None:
            return False
        if id(each) not in seen:
            seen.add(id(each))
            pending.extend(held)
    return True


def _held(value: object, kind: type) -> list[object] | None:
    """A list's or tuple's items, or a dict's keys and values, plain or tracked; None for a value
    of any other type."""
    if kind is list or kind is ConcolicList:
        return list(list.__iter__(cast(list[object], value)))
    if kind is tuple:
        return list(tuple.__iter__(cast(tuple[object, ...], value)))
    if kind is dict or kind is ConcolicDict:
        pairs = dict.items(cast(dict[object, object], value))
        return [part for pair in pairs for part in pair]
    return None
