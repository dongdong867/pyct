"""The tuples of a seed and the values the walk does not follow, each placed once every path
is walked: a tuple built from its items, and a value copied whole, each once and put everywhere
the walk put it. A tuple is built after every tuple and every value held back among its items,
and a held-back value's copy holds the tuple the walk builds.
"""

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
    """What the walk places where a value goes once every path is walked: a tuple, or a copy
    of a value the walk does not follow."""

    VALUE = "placed once every path is walked"


@dataclass(eq=False)
class TupleBuild:
    """One tuple of the seed, built once every path is walked.

    ``items`` is the list its items are placed in by its last visit, which ``named`` says named
    them, and ``placements`` every place the walk put it, where the one tuple its build makes,
    ``made``, goes.
    """

    value: tuple[object, ...]
    named: bool = False
    visited: bool = False
    visiting: bool = False
    items: list[object] = field(default_factory=list)
    placements: list[tuple[Holder, Slot]] = field(default_factory=list)
    made: tuple[object, ...] | None = None


@dataclass(eq=False)
class PlainCopy:
    """A value the walk does not follow, copied whole once every path is walked, and every
    place the walk put it. ``copying`` is set while its deepcopy runs and ``done`` once its
    copy, ``made``, is put everywhere; ``used_by`` is each tuple built with its copy part
    made."""

    value: object
    placements: list[tuple[Holder, Slot]] = field(default_factory=list)
    copying: bool = False
    done: bool = False
    made: object = None
    used_by: list[TupleBuild] = field(default_factory=list)


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


def held_among(
    plain: Iterable[PlainCopy], owners: Mapping[int, TupleBuild]
) -> dict[int, list[PlainCopy]]:
    """The values held back among each tuple's items, by the tuple's identity."""
    among: dict[int, list[PlainCopy]] = {}
    for each in plain:
        for owner in _owners_of(each.placements, owners):
            among.setdefault(id(owner), []).append(each)
    return among


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
