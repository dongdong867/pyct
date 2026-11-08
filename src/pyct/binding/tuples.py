"""The tuples of a seed and the values the walk does not follow, each placed once every path
is walked: a tuple built from its items, innermost first, and a value copied whole after them,
each put everywhere the walk put it.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pyct.binding import objects
from pyct.binding.objects import Held

# where the walk puts a value: a dict's copy, a list's, the list a tuple's items are placed in
# before the tuple is built, or an object's copy
type Holder = dict[Any, object] | list[object] | Held

# where in its holder a value goes: an index for a list, for a dict the copy's own key, and
# for an object an ``Attribute``
type Slot = Hashable


class Later(Enum):
    """What the walk places where a value goes once every path is walked: a tuple, or a copy
    of a value the walk does not follow."""

    VALUE = "placed once every path is walked"


@dataclass(eq=False)
class TupleBuild:
    """One tuple of the seed, built once every path is walked.

    ``items`` is the list its items are placed in by its last visit, which ``named`` says named
    them, and ``placements`` every place the walk put it, where the one tuple its build makes
    goes.
    """

    value: tuple[object, ...]
    named: bool = False
    visited: bool = False
    visiting: bool = False
    items: list[object] = field(default_factory=list)
    placements: list[tuple[Holder, Slot]] = field(default_factory=list)


@dataclass(eq=False)
class PlainCopy:
    """A value the walk does not follow, copied whole once every tuple it may hold is built,
    and every place the walk put it."""

    value: object
    placements: list[tuple[Holder, Slot]] = field(default_factory=list)


def buildable(value: tuple[object, ...]) -> bool:
    """Whether ``tuple.__new__`` builds a tuple of this one's type that loses nothing of it.

    A tuple, or a subclass that copies by Python's default route and whose
    instance holds nothing in a ``__dict__``, a namedtuple and one with
    methods of its own say. A struct sequence such as ``time.struct_time``
    refuses to be built so.
    """
    kind = type(value)
    if kind is tuple:
        return True
    if not objects.copies_by_default(kind) or objects.own_fields(value):
        return False
    try:
        tuple.__new__(kind, ())
    except TypeError:
        return False
    return True


def innermost_first(
    builds: Iterable[TupleBuild], owners: Mapping[int, TupleBuild]
) -> list[TupleBuild]:
    """The tuples in an order that builds each after every tuple its items hold."""
    inside: dict[int, list[TupleBuild]] = {}
    for build in builds:
        for owner in _owners_of(build.placements, owners):
            inside.setdefault(id(owner), []).append(build)
    order: list[TupleBuild] = []
    done: set[int] = set()
    for build in builds:
        stack = [(build, False)]
        while stack:
            each, ready = stack.pop()
            if ready:
                order.append(each)
            elif id(each) not in done:
                done.add(id(each))
                stack.append((each, True))
                stack.extend((inner, False) for inner in inside.get(id(each), ()))
    return order


def holding(
    order: list[TupleBuild], plain: Iterable[PlainCopy], owners: Mapping[int, TupleBuild]
) -> set[int]:
    """The tuples that hold a value held back, themselves or through a tuple their items hold,
    by identity, given the tuples innermost first."""
    waiting = {id(owner) for each in plain for owner in _owners_of(each.placements, owners)}
    for build in order:
        if id(build) in waiting:
            waiting.update(id(owner) for owner in _owners_of(build.placements, owners))
    return waiting


def _owners_of(
    placements: Iterable[tuple[Holder, Slot]], owners: Mapping[int, TupleBuild]
) -> Iterable[TupleBuild]:
    """The tuples whose items a value was placed among, by their last visit: an item list an
    earlier visit filled belongs to a build no tuple is made from."""
    for into, _ in placements:
        owner = owners.get(id(into))
        if owner is not None and into is owner.items:
            yield owner
