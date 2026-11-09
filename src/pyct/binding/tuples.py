"""The tuples of a seed, each built once every path is walked, from its items and after every
tuple among them, and put everywhere the walk put it; and where the walk puts a value."""

from __future__ import annotations

from collections.abc import Hashable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, SupportsIndex, cast

from pyct.binding import objects
from pyct.binding.objects import Attribute, Held

# where the walk puts a value: a dict's copy, a list's, the list a tuple's items are placed in
# before the tuple is built, or an object's copy
type Holder = dict[Any, object] | list[object] | Held

# where in its holder a value goes: an index for a list, for a dict the copy's own key, and
# for an object an ``Attribute``
type Slot = Hashable


class Later(Enum):
    """What the walk places where a tuple goes, until the tuple is built once every path is
    walked."""

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


def buildable(value: tuple[object, ...]) -> bool:
    """Whether ``tuple.__new__`` builds a tuple of this one's type that loses nothing of it.

    A tuple, or a subclass whose instance holds nothing in a ``__dict__``, a
    namedtuple and one with methods of its own say. No copy or pickling hook
    of the class runs, so none is read. A struct sequence such as
    ``time.struct_time`` refuses to be built so.
    """
    kind = type(value)
    if kind is tuple:
        return True
    if objects.own_fields(value):
        return False
    try:
        tuple.__new__(kind, ())
    except TypeError:
        return False
    return True


def tuples_among(
    builds: Sequence[TupleBuild], owners: Mapping[int, TupleBuild]
) -> dict[int, list[TupleBuild]]:
    """The tuples among each tuple's items, by the tuple's identity."""
    inside: dict[int, list[TupleBuild]] = {}
    for build in builds:
        for owner in _owners_of(build.placements, owners):
            inside.setdefault(id(owner), []).append(build)
    return inside


def innermost_first(
    builds: Sequence[TupleBuild], inside: Mapping[int, list[TupleBuild]]
) -> list[TupleBuild]:
    """The tuples in an order that builds each after every tuple its items hold."""
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
    order: Sequence[TupleBuild],
    placements: Iterable[tuple[Holder, Slot]],
    owners: Mapping[int, TupleBuild],
) -> set[int]:
    """The tuples among whose items a value was placed at one of ``placements``, themselves
    or through a tuple their items hold, by identity, given the tuples innermost first."""
    found = {id(owner) for owner in _owners_of(placements, owners)}
    for build in order:
        if id(build) in found:
            found.update(id(owner) for owner in _owners_of(build.placements, owners))
    return found


def _owners_of(
    placements: Iterable[tuple[Holder, Slot]], owners: Mapping[int, TupleBuild]
) -> Iterable[TupleBuild]:
    """The tuples whose items a value was placed among, by their last visit: an item list an
    earlier visit filled belongs to a build no tuple is made from."""
    for into, _ in placements:
        owner = owners.get(id(into))
        if owner is not None and into is owner.items:
            yield owner


def put(into: Holder, slot: Slot, placed: object, value: object) -> None:
    """Put a placed value in its holder. An attribute the walk hands on as it came keeps what
    deepcopy made of it."""
    if isinstance(into, Held):
        if placed is not value:
            cast(Attribute, slot).write(into.made, placed)
    elif isinstance(into, list):
        list.__setitem__(into, cast(SupportsIndex, slot), placed)
    else:
        dict.__setitem__(into, slot, placed)
