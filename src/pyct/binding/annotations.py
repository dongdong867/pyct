"""What an annotation asks of a seed value, and every value in a seed that contradicts it."""

import json
import typing
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

# the types a value is checked against as it stands, matched by identity
PLAIN: tuple[type, ...] = (str, int, float, bool)


@dataclass(frozen=True)
class Items:
    """A list or dict annotation: the kind, and what each item or value must be.

    ``each`` is None for a bare ``list`` or ``dict``, which checks the kind alone.
    """

    kind: type
    each: "Check | None"


# what an annotation asks of a value: one of the plain types, or a list or dict of checked items
type Check = type | Items


def check_of(annotation: object) -> Check | None:
    """What an annotation asks of a seed value, or None when it asks nothing pyct checks.

    A bare ``str``, ``int``, ``float`` or ``bool`` asks for that type, matched
    by identity, so an annotation that merely compares equal to one is not
    it. A bare ``list`` or ``dict`` asks for the kind. ``list[X]`` and
    ``dict[str, X]`` also ask every item or value for X, where X is itself one
    of these. JSON keys are always strings, so a dict annotation is read only
    when it says so. Every other annotation asks nothing.
    """
    for plain in PLAIN:
        if annotation is plain:
            return plain
    if annotation is list or annotation is dict:
        return Items(annotation, None)
    origin = typing.get_origin(annotation)
    arguments = typing.get_args(annotation)
    if origin is list and len(arguments) == 1:
        return _of_items(list, arguments[0])
    if origin is dict and len(arguments) == 2 and arguments[0] is str:
        return _of_items(dict, arguments[1])
    return None


def _of_items(kind: type, item: object) -> Items | None:
    """A list or dict whose items must fit ``item``, or None when ``item`` asks nothing."""
    each = check_of(item)
    return None if each is None else Items(kind, each)


def contradictions(checks: Mapping[str, Check], seed: Mapping[str, object]) -> list[str]:
    """One line per value in the seed that Python's own typing would not accept.

    Parameters come in the order of ``checks``, which is signature order, and
    the items of a list or dict in the seed's order. A value passes when it
    is an instance of the type asked for, plus the one allowance Python makes
    itself: an ``int`` stands in where a ``float`` is asked for. ``bool``
    being a subclass of ``int`` is Python's rule too, so ``True`` passes
    ``int`` while ``1`` fails ``bool``. A value is named by the access that
    reaches it, as Python writes it, ``cfg['a'][1]``, and spelled as JSON
    because the seed was typed as JSON.
    """
    return [
        line
        for name, check in checks.items()
        if name in seed
        for line in _refused(check, seed[name], name)
    ]


def _refused(check: Check, value: object, written: str) -> list[str]:
    """The lines for one value and everything under it. ``written`` is its access."""
    if isinstance(check, type):
        return [] if _accepts(check, value) else [_refusal(written, check, value)]
    entries = _entries(check.kind, value)
    if entries is None:
        return [_refusal(written, check.kind, value)]
    if check.each is None:
        return []
    each = check.each
    return [line for key, item in entries for line in _refused(each, item, f"{written}[{key!r}]")]


def _entries(kind: type, value: object) -> Iterable[tuple[object, object]] | None:
    """A list's items by index or a dict's values by key, or None for a value of another kind."""
    if kind is list and isinstance(value, list):
        return enumerate(value)
    if kind is dict and isinstance(value, dict):
        return value.items()
    return None


def _accepts(hint: type, value: object) -> bool:
    return isinstance(value, hint) or (hint is float and isinstance(value, int))


def _refusal(written: str, hint: type, value: object) -> str:
    article = "an" if hint is int else "a"
    return f"{written} must be {article} {hint.__name__}, got {json.dumps(value)}"
