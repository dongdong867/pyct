"""What an annotation asks of a seed value, and every value in a seed that contradicts it."""

import json
import re
import types
import typing
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pyct.binding.places import step_in

# the types a value is checked against as it stands, matched by identity
PLAIN: tuple[type, ...] = (str, int, float, bool)

# the kind of None, which a union of plain types may hold beside them: JSON's null
NONE = type(None)

# an int key as JSON writes it: the text an input's line holds for a dict's int key
_INT_TEXT = re.compile(r"0|-?[1-9][0-9]*")


def int_keys(check: "Check | None") -> bool:
    """Whether a dict's annotation names int keys, which the seed binding reads its keys as."""
    return isinstance(check, Items) and check.kind is dict and check.keys is int


def reads_as_int(key: object) -> bool:
    """Whether a key is the text JSON writes for an int, which a ``dict[int, X]`` reads back as
    the int."""
    return type(key) is str and _INT_TEXT.fullmatch(key) is not None


@dataclass(frozen=True)
class Items:
    """A list or dict annotation: the kind, and what each item or value must be.

    ``each`` is None when the annotation's items ask nothing pyct checks, a
    bare ``list`` or ``list[Any]`` say, and then only the kind is checked.
    ``keys`` is a dict's key type as the annotation names it, ``str`` when it
    names none. A dict whose keys are not strs is not checked, since JSON
    keys are always strings; its keys are read back by it instead (see
    ``walk``). ``fixed`` marks a ``list[C]`` or ``dict[str, C]`` hint whose
    ``each`` is a class to build, one that names no one class, or such a list
    or dict itself (``hints``): such a list keeps its length and such a dict
    its keys, and each value is named by its place and takes ``each``.
    """

    kind: type
    each: "Check | None"
    keys: object = str
    fixed: bool = False


def item_check(check: "Check | None", kind: type, key: object) -> "Check | None":
    """What ``check`` asks of the value at ``key`` in a list or dict of ``kind``: a constructor
    parameter's check by its index or key (``Fields``), or a list or dict annotation's check of
    each item when the annotation is of that kind (``Items``). The walk and the traversal of
    the objects a call builds read this one rule."""
    if isinstance(check, Fields):
        return check.each.get(key)
    return check.each if isinstance(check, Items) and check.kind is kind else None


@dataclass(frozen=True)
class OneOf:
    """A union of plain types, and of None, as the items of a list or dict: any one of them."""

    kinds: tuple[type, ...]


@dataclass(frozen=True)
class Fields:
    """A dict whose keys are fixed, or a list whose length is: a constructor's arguments, which
    pyct unpacks itself.

    Its values are tracked and named by their keys or indexes, as a dict's
    or a list's values are, while the container itself is not, so no answer
    adds a key or an item, drops one or changes its length. ``each`` is what
    each key's own annotation asks of its value.
    """

    # by a dict's str keys, or by a list's indexes
    each: Mapping[Any, "Check"]


@dataclass(frozen=True)
class Builds:
    """A class hint the value under it is built as, from a JSON object or list: the class."""

    cls: type


@dataclass(frozen=True)
class NoOneClass:
    """A class hint that names no one class to build, an abstract class say, and why."""

    reason: str


# what an annotation asks of a value: a plain type, a list or dict, or, for an item, a union;
# what the arguments a method's instance is built from ask; and a class a hint builds
type Check = type | Items | OneOf | Fields | Builds | NoOneClass


def check_of(annotation: object) -> Check | None:
    """What an annotation asks of a seed value, or None when it asks nothing pyct checks.

    A bare ``str``, ``int``, ``float`` or ``bool`` asks for that type, matched
    by identity, so an annotation that merely compares equal to one is not
    it. A list or dict annotation asks for the kind whatever its items are
    (see ``_of_items``). JSON keys are always strings, so a dict annotation
    whose key type is not ``str`` checks nothing, and only says the key type.
    Every other annotation, a union among them, asks nothing.
    """
    for plain in PLAIN:
        if annotation is plain:
            return plain
    if annotation is list or annotation is dict:
        return Items(annotation, None)
    origin = typing.get_origin(annotation)
    arguments = typing.get_args(annotation)
    if origin is list:
        return Items(list, _of_items(arguments[0]) if len(arguments) == 1 else None)
    if origin is dict and not arguments:
        return Items(dict, None)
    if origin is dict and len(arguments) == 2 and arguments[0] is str:
        return Items(dict, _of_items(arguments[1]))
    if origin is dict and len(arguments) == 2:
        values = _of_items(arguments[1]) if arguments[0] is int else None
        return Items(dict, values, keys=arguments[0])
    return None


def _of_items(item: object) -> Check | None:
    """What each item of a list or dict must be, or None when its annotation asks nothing.

    An item is checked as a parameter is, and also against a union of plain
    types and None, ``int | None`` say, where ``null`` passes. A union as a
    parameter's own annotation is not checked.
    """
    check = check_of(item)
    if check is not None:
        return check
    origin = typing.get_origin(item)
    kinds = typing.get_args(item)
    if origin is not typing.Union and origin is not types.UnionType:
        return None
    if all(any(kind is plain for plain in (*PLAIN, NONE)) for kind in kinds):
        return OneOf(kinds)
    return None


def contradictions(
    checks: Mapping[str, Check],
    seed: Mapping[str, object],
    place: str | None = None,
    built: Collection[int] = frozenset(),
) -> list[str]:
    """One line per value in the seed that Python's own typing would not accept.

    Parameters come in the order of ``checks``, which is signature order, and
    the items of a list or dict in the seed's order. A value passes when it
    is an instance of the type asked for, plus the one allowance Python makes
    itself: an ``int`` stands in where a ``float`` is asked for. ``bool``
    being a subclass of ``int`` is Python's rule too, so ``True`` passes
    ``int`` while ``1`` fails ``bool``. A value is named by the access that
    reaches it, as Python writes it, ``cfg['a'][1]``, and spelled as JSON
    because the seed was typed as JSON, printable text as it was typed, so the
    value can be found on the command line that gave it (see ``as_typed``).
    With a ``place``, the seed is the object there, and each value is named
    one step further in from it, ``self['owner']``. A value whose identity is
    in ``built``, an object each input builds, gives no line, at any depth.
    """
    return [
        line
        for name, check in checks.items()
        if name in seed
        for line in refused(
            check, seed[name], name if place is None else step_in(place, name), built
        )
    ]


def refused(
    check: Check, value: object, written: str, built: Collection[int] = frozenset()
) -> list[str]:
    """The lines for one value and everything under it. ``written`` is its access.

    A dict whose keys are not strs gives none, and so do ``Fields``, ``Builds`` and
    ``NoOneClass``, which ``checked_annotations`` never makes with ``check_of``, and so does a
    value in ``built``.
    """
    if id(value) in built:
        return []
    if isinstance(check, Fields | Builds | NoOneClass):
        return []
    if isinstance(check, Items) and check.keys is not str:
        return []
    if isinstance(check, type):
        check = OneOf((check,))
    if isinstance(check, OneOf):
        if any(_accepts(kind, value) for kind in check.kinds):
            return []
        return [_refusal(written, check.kinds, value)]
    entries = _entries(check.kind, value)
    if entries is None:
        return [_refusal(written, (check.kind,), value)]
    if check.each is None:
        return []
    each = check.each
    return [
        line for key, item in entries for line in refused(each, item, step_in(written, key), built)
    ]


def _entries(kind: type, value: object) -> Iterable[tuple[object, object]] | None:
    """A list's items by index or a dict's values by key, or None for a value of another kind."""
    if kind is list and isinstance(value, list):
        return enumerate(value)
    if kind is dict and isinstance(value, dict):
        return value.items()
    return None


def _accepts(hint: type, value: object) -> bool:
    return isinstance(value, hint) or (hint is float and isinstance(value, int))


def _refusal(written: str, kinds: tuple[type, ...], value: object) -> str:
    return f"{written} must be {_wanted(kinds)}, got {as_typed(value)}"


def as_typed(value: object) -> str:
    """The value as JSON, printable text as it was typed and every other character escaped.

    A line separator, a control or a bidi override would break or reorder
    the line, so each is written as JSON escapes it, in UTF-16 units as JSON
    does past U+FFFF.
    """
    return "".join(
        character if character.isprintable() else _escaped(character)
        for character in json.dumps(value, ensure_ascii=False)
    )


def _escaped(character: str) -> str:
    units = character.encode("utf-16-be", "surrogatepass")
    return "".join(f"\\u{units[i]:02x}{units[i + 1]:02x}" for i in range(0, len(units), 2))


def _wanted(kinds: tuple[type, ...]) -> str:
    """What a value must be, as a person says it: ``an int``, ``an int or null``."""
    named = [_named(kind) for kind in kinds]
    if len(named) == 1:
        return named[0]
    if len(named) == 2:
        return f"{named[0]} or {named[1]}"
    return f"{', '.join(named[:-1])}, or {named[-1]}"


def _named(kind: type) -> str:
    """A type as the refusal names it: ``an int``, ``a str``, and None as JSON's ``null``."""
    if kind is NONE:
        return "null"
    return f"{'an' if kind is int else 'a'} {kind.__name__}"
