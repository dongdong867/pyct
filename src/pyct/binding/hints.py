"""A class hint, read as the class each input builds the value under it as, and what the values
inside such an object ask: its constructor's own hints, read where they were written.

A hint builds when it names one class pyct can call: a plain class, a dataclass, a
namedtuple, a C class, or a parameterized generic class, which builds its origin. A class
from ``builtins``, ``typing`` or ``collections``, a base of ``list`` or ``dict`` and a subclass
of either keep the JSON value, and read as ``check_of`` reads them. A Protocol, an abstract
class and a union of two classes name no one class. A ``list[X]`` or ``dict[str, X]`` whose
``X`` builds, names no one class, or is such a list or dict itself, is a fixed ``Items``:
each item or value is built, and the list keeps its length and the dict its keys.
"""

from __future__ import annotations

import functools
import inspect
import types
import typing
from collections.abc import Callable
from dataclasses import dataclass

from pyct.binding.annotations import (
    NONE,
    PLAIN,
    Builds,
    Check,
    Fields,
    Items,
    NoOneClass,
    check_of,
)
from pyct.binding.call import by_position
from pyct.binding.classes import is_a_class, signature_of
from pyct.binding.resolve import as_text, checked_annotations, resolved

# the modules whose classes keep the JSON value: the types JSON gives, typing's own forms, and
# the containers of collections, which a JSON value would build wrong: deque(1, 2, 3)
_KEPT_MODULES = frozenset({"builtins", "typing", "collections"})

# what every reason a hint builds no one class ends with
_NAME_IT = 'name the class to build with "__class__"'

# a union's count of classes as a word, from two
_COUNTS = ("two", "three", "four", "five", "six", "seven", "eight", "nine")

# the parameters a key never fills by its own name
_STARRED = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)

# each class's inside, by the class's identity; the class is kept beside it, so its identity
# is not reused
_INSIDES: dict[int, tuple[type, Inside]] = {}


@dataclass(frozen=True)
class Inside:
    """What the values inside an object of one class ask: each keyword's check by its name, and
    each positional item's by its index."""

    keys: Fields
    items: Fields


# what an object of a class whose constructor asks nothing holds
NOTHING = Inside(Fields({}), Fields({}))


def hint_check(annotation: object, owner: object = None) -> Check | None:
    """What a resolved hint asks: the class it builds, why it names no one class, or what
    ``check_of`` makes of it. A hint whose test raises asks nothing.

    With the ``owner`` the hint was written on, a quoted name in it is read
    in the modules that could have written it (``resolved``): one a hint
    kept as text evaluates to, ``"C"`` under ``from __future__ import
    annotations``, and one inside a union, ``Optional["C"]``. With none, a
    quoted name asks nothing.
    """
    try:
        return _read(annotation, owner)
    except Exception:
        return None


def hints_of(owner: object) -> Callable[[object], Check | None]:
    """The hint reader for the hints written on ``owner`` (``hint_check``)."""
    return functools.partial(hint_check, owner=owner)


def _read(annotation: object, owner: object) -> Check | None:
    if owner is not None and isinstance(as_text(annotation), str):
        # read once more: a quoted name that evaluates to text again asks nothing
        return resolved(annotation, owner, functools.partial(_read_named, owner=owner))
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        members = tuple(_member(member, owner) for member in typing.get_args(annotation))
        return _union(annotation, members)
    named = _named(annotation)
    if named is not None:
        return named
    fixed = _fixed(annotation, owner)
    return check_of(annotation) if fixed is None else fixed


def _fixed(annotation: object, owner: object) -> Items | None:
    """A ``list[X]`` or ``dict[str, X]`` whose ``X`` reads as a class to build, as one that
    names no one class, or as such a list or dict itself; None for any other hint."""
    origin = typing.get_origin(annotation)
    arguments = typing.get_args(annotation)
    if origin is list and len(arguments) == 1:
        kind, item = list, arguments[0]
    elif origin is dict and len(arguments) == 2 and arguments[0] is str:
        kind, item = dict, arguments[1]
    else:
        return None
    each = _read(item, owner)
    if isinstance(each, Builds | NoOneClass) or (isinstance(each, Items) and each.fixed):
        return Items(kind, each, fixed=True)
    return None


def _read_named(annotation: object, owner: object) -> Check | None:
    """What a quoted name's value asks, when that value is no text itself."""
    return None if isinstance(as_text(annotation), str) else _read(annotation, owner)


def _member(member: object, owner: object) -> object:
    """A union's member, a quoted name read in the ``owner``'s modules when it resolves."""
    if owner is None or not isinstance(member, typing.ForwardRef):
        return member
    found = resolved(member, owner, _same)
    return member if found is None else found


def _same(value: object) -> object:
    return value


def _named(annotation: object) -> Builds | NoOneClass | None:
    """The class a hint builds or why it names no one class, or None for a hint that is no
    class, or a class that keeps the JSON value."""
    cls = annotation if is_a_class(annotation) else typing.get_origin(annotation)
    if not is_a_class(cls) or cls.__module__ in _KEPT_MODULES:
        return None
    # the mark typing sets on a Protocol, which typing.is_protocol reads on 3.13 and later;
    # tested first, since a subclass test of a Protocol raises
    if getattr(cls, "_is_protocol", False) is True:
        return NoOneClass(f"hint {cls.__qualname__} is a Protocol; {_NAME_IT}")
    if issubclass(cls, (list, dict)) or issubclass(list, cls) or issubclass(dict, cls):
        return None
    if inspect.isabstract(cls):
        return NoOneClass(f"hint {cls.__qualname__} is an abstract class; {_NAME_IT}")
    return Builds(cls)


def _union(annotation: object, members: tuple[object, ...]) -> Check | None:
    """A union: its one class when only None and plain types stand beside it, why it names no
    one class when it names two or more, and what ``check_of`` makes of it otherwise."""
    classes: list[Builds | NoOneClass] = []
    others = False
    for member in members:
        if member is NONE or any(member is plain for plain in PLAIN):
            continue
        named = _named(member)
        if named is None:
            others = True
        else:
            classes.append(named)
    if len(classes) > 1:
        count = _COUNTS[len(classes) - 2] if len(classes) < 10 else str(len(classes))
        written = " | ".join(_written(member) for member in members)
        return NoOneClass(f"hint {written} names {count} classes; {_NAME_IT}")
    if classes and not others:
        return classes[0]
    return check_of(annotation)


def _written(member: object) -> str:
    """A union's member as a reason writes it: a class by its qualified name, the origin's for
    a parameterized one, None as None, any other as Python formats an annotation."""
    if member is NONE:
        return "None"
    if _named(member) is not None:
        cls = member if is_a_class(member) else typing.get_origin(member)
        return typing.cast(type, cls).__qualname__
    return inspect.formatannotation(member)


def inside_of(cls: type) -> Inside:
    """What the values inside an object of ``cls`` ask, read once per class.

    Each hint of its constructor is read with ``hint_check`` where it was
    written (``checked_annotations``): a keyword's check by its parameter, an
    item's by the parameter at its position, and none for ``*args`` or
    ``**kwargs``. A class whose signature Python cannot read asks nothing.
    One level is read at a time, so a class whose hint names itself is read
    once.
    """
    known = _INSIDES.get(id(cls))
    if known is None:
        known = _INSIDES[id(cls)] = (cls, _read_inside(cls))
    return known[1]


def _read_inside(cls: type) -> Inside:
    signature = signature_of(cls)
    if signature is None:
        return NOTHING
    checks = checked_annotations(signature, cls, hints_of(cls))
    parameters = signature.parameters
    keys = {name: each for name, each in checks.items() if parameters[name].kind not in _STARRED}
    items = {
        at: checks[parameter.name]
        for at, parameter in enumerate(by_position(signature))
        if parameter.name in checks
    }
    return Inside(Fields(keys), Fields(items))
