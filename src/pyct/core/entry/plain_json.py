"""A value as plain JSON data: what a call on model-written code answers (`pyct.run.model_runs`),
and what a name holds as a piece of the target's code starts or ends (`pyct.core.entry.pieces`).

Each part is read through its base type, chosen by the part's own type, so
nothing is recorded and no method of the value runs.
"""

from __future__ import annotations

from typing import Any

from pyct.core.lists.list_state import plain


def plain_json(value: object, *, tuples: bool = True, most: int | None = None) -> object:
    """The value as plain JSON data: each tracked scalar as its plain value, a list as a list, a
    tuple as a list when ``tuples`` says so, and a dict with str keys as an object.

    Raises TypeError for a part JSON holds no form of. With ``most``, raises
    ValueError once the parts read, each counted once and a str by its
    length too, come to more than ``most``: a value whose JSON text is
    shorter than ``most`` never comes to more.
    """
    return _Reading(tuples, most).of(value)


class _Reading:
    """One value's reading: whether a tuple is a list, and what is left of the count to read.

    A plain class, as a dataclass takes long to make, and every substituted
    module imports this one as it first loads.
    """

    __slots__ = ("left", "tuples")

    def __init__(self, tuples: bool, left: int | None) -> None:  # noqa: FBT001
        self.tuples = tuples
        self.left = left

    def of(self, value: object) -> object:
        """One part, and those inside it."""
        # read by its own type alone, never by `isinstance`, which can ask it for `__class__`
        held: Any = plain(value)
        self._count(1)
        kind = type(held)
        if held is None or kind is bool:
            return held
        if issubclass(kind, int):
            return int.__int__(held)
        if issubclass(kind, float):
            return float.__float__(held)
        if issubclass(kind, str):
            self._count(str.__len__(held))
            return str.__str__(held)
        if issubclass(kind, list):
            return [self.of(item) for item in list.__iter__(held)]
        if self.tuples and issubclass(kind, tuple):
            return [self.of(item) for item in tuple.__iter__(held)]
        if issubclass(kind, dict):
            return {_key(key): self.of(item) for key, item in dict.items(held)}
        raise TypeError(f"{kind.__name__} is not a JSON value")

    def _count(self, parts: int) -> None:
        if self.left is None:
            return
        self.left -= parts
        if self.left < 0:
            raise ValueError("the value holds more than JSON text of the length asked for")


def _key(key: object) -> str:
    held: Any = plain(key)
    if not issubclass(type(held), str):
        raise TypeError(f"a key of type {type(held).__name__} is not one a JSON object holds")
    return str.__str__(held)
