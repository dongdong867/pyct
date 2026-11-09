"""One walk of a seed: every dict, list and tuple rebuilt, the attributes of each object whose
class passes the copy rule (``objects``) followed, and every value bind tracks handed to a
visitor.

bind, the seed's leaves and the model all read this one walk, so they cannot disagree about
which values are tracked, what each is named, or which lists and dicts are tracked whole.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol, TypeGuard, cast

from pyct.binding import objects
from pyct.binding.annotations import Check, Fields
from pyct.binding.builds import holding_forms, object_form
from pyct.binding.copies import Scratch, faithful_copies
from pyct.binding.objects import Attributes, Held
from pyct.binding.steps import FIXED, Pending, form_items, items_to_place, keyed, step
from pyct.binding.tuples import (
    Holder,
    Later,
    Slot,
    TupleBuild,
    among_items,
    buildable,
    holding,
    innermost_first,
    put,
    tuples_among,
)
from pyct.core.foundation.branch import Expression


@dataclass(frozen=True)
class Place:
    """Where the walk puts a value: its access, the holder it goes in and its slot there, what
    its annotation asks of it, and whether that holder is a tracked list."""

    access: Expression
    into: Holder
    slot: Slot
    check: Check | None
    in_list: bool


class Visitor(Protocol):
    """What one kind of walk makes of the values it tracks and the lists it tracks whole."""

    def scalar(self, value: int | float | str, place: Place) -> object:
        """What stands where a tracked int, str or float was."""
        ...

    def listed(self, value: list[object], place: Place) -> tuple[list[object], list[object]]:
        """The copy that stands for a tracked list, and the items it takes, in order."""
        ...

    def mapped(
        self, value: dict[object, object], place: Place
    ) -> tuple[dict[object, object], dict[object, object]]:
        """The copy that stands for a tracked dict, and the items it takes, in order: the copy
        holds each of their keys, in the same order."""
        ...


# the types bind tracks inside an argument, themselves and none of their subclasses
_TRACKED_INSIDE: frozenset[type] = frozenset({int, float, str, bool})


def binds(value: object, access: Expression) -> TypeGuard[int | float | str]:
    """Whether bind tracks this value at this access: the one rule the walk reads.

    An int, a str, a float and a bool are tracked as an argument's own value, a subclass of
    one of them too. Inside a dict, a list, a tuple or an object only those four types
    themselves are: a subclass there, an enum member say, passes through as it came, since no
    sort declares a value that may be anything else as well.
    """
    if isinstance(access, str):
        return isinstance(value, int | float | str)
    return type(value) in _TRACKED_INSIDE


# the types whose values the walk hands on as they are: nothing can change one
_ATOMIC: frozenset[type] = frozenset({int, float, str, bool, type(None)})

# what a container or an object takes from the walk into its copy: a list's items, a dict's,
# or an object's attributes
type _Insides = list[object] | dict[object, object] | Attributes


class Walk:
    """One walk of a seed, in seed order, depth first, and never recursive.

    A list of what is left to place stands in for Python's call stack, so a
    seed of dicts, lists and tuples nested past Python's recursion limit is
    walked like any other. A value the walk copies with ``copy.deepcopy``, an
    object, a subclass of dict or list, or a value it does not follow, is
    refused when what it holds nests past that limit, a chain of objects or a
    deep dict an object holds say, and stays as it came. Each dict, list and
    tuple the walk rebuilds, and each object it copies, is remembered by the
    identity of the seed's own, so one reached again, by a second path or
    from inside itself, is the same copy. Its values are named by the first
    path in seed order that names anything: a copy first reached under a key
    no access can name is walked again, into the same copy, when a path that
    names it reaches it. Each is walked at most twice, so the walk ends.

    A list first reached under a name is tracked whole: the visitor makes its
    copy and says which items it takes, and every value placed in it is a
    value inside a tracked list. An object whose class passes the copy rule
    (``objects.copies_by_default``), a subclass of dict or list among them,
    is copied by deepcopy with a memo that reads the walk's copies, and its
    attributes, or its items, are then followed into that copy, so the
    objects inside it are its copies from that one deepcopy. Only a faithful
    copy is gone into, at any depth (``copies.faithful_copies``); the walk
    does not go into any other, which is handed on as deepcopy made it.

    A tuple's items are placed by index in a list of their own. Once every
    path is walked, each tuple is built once from its items, of its own type,
    innermost first, and each value the walk does not follow is copied whole
    by deepcopy over the walk's copies, so it holds the walk's copy of each
    object, list and dict the walk copied, and nothing else it holds is tracked;
    one deepcopy refuses stays as it came. A tuple inside a value copied
    whole is a copy of its own. Each goes everywhere the walk put it (see
    ``_finish`` for the order).
    """

    def __init__(self, visitor: Visitor) -> None:
        self._visitor = visitor
        # each copy by the identity of the seed's value, which is kept alive beside it so its
        # identity is not reused, the containers whose copies a path names, and the copies
        # that are tracked lists. The copies are what deepcopy finds before it copies a value
        self._copies: dict[int, object] = {}
        self._kept: list[object] = []
        self._named: set[int] = set()
        self._tracked: set[int] = set()
        # the objects whose copy is handed on plain, by the identity of the seed's
        self._whole: set[int] = set()
        # the copies of fixed shape, the object forms among them, whose values may be object forms
        self._fixed: set[int] = set()
        self._forms: set[int] = set()
        # the seed's lists and dicts that hold an object form, by identity: their shape is fixed
        self._holding: set[int] = set()
        # each dict subclass's keys in the order its copy holds them, by the identity of the seed's
        self._keys: dict[int, list[object]] = {}
        # each tuple by the identity of the seed's, and by the identity of each list its items
        # were placed in
        self._tuples: dict[int, TupleBuild] = {}
        self._owners: dict[int, TupleBuild] = {}
        self._pending: list[Pending | TupleBuild] = []
        # each value to copy whole and where it goes, in walk order
        self._to_copy: list[tuple[object, Holder, Slot]] = []

    def rebuilt(
        self, seed: Mapping[str, object], checks: Mapping[str, Check] | None = None
    ) -> dict[str, object]:
        """The seed as the walk rebuilds it, one parameter per key, each with its annotation's
        check when ``checks`` names one."""
        asked = checks or {}
        self._holding = holding_forms(seed)
        rebuilt: dict[str, object] = dict.fromkeys(seed)
        self._later((value, name, rebuilt, name, asked.get(name)) for name, value in seed.items())
        while self._pending:
            entry = self._pending.pop()
            if isinstance(entry, TupleBuild):
                entry.visiting = False
                continue
            value, access, into, slot, check = entry
            in_list = id(into) in self._tracked
            placed = self._placed(value, access, Place(access, into, slot, check, in_list))
            if placed is not Later.VALUE:
                put(into, slot, placed, value)
        self._finish()
        return rebuilt

    def _later(self, values: Iterable[Pending]) -> None:
        """Queue values to place in the order given: the stack pops the last one first."""
        self._pending.extend(reversed(list(values)))

    def _placed(self, value: object, access: Expression | None, place: Place) -> object:
        """What goes where ``value`` was: its tracked form, its copy, the value itself, or
        ``Later.VALUE`` for a value copied whole or a tuple built once every path is walked. A
        value with no access is never tracked, and neither is anything under it."""
        if access is not None and binds(value, access):
            return self._visitor.scalar(value, place)
        if type(value) in _ATOMIC:
            return value
        if isinstance(value, tuple):
            if buildable(value):
                return self._visit_tuple(value, access, place)
            return self._copy_later(value, place)
        if type(value) is list or type(value) is dict or objects.followed(value):
            return self._followed(value, access, place)
        return self._copy_later(value, place)

    def _followed(self, value: object, access: Expression | None, place: Place) -> object:
        """A dict's, a list's or an object's copy, its items or attributes queued."""
        made = self._copies.get(id(value))
        form = self._form(value, made, place)
        check = FIXED if form else place.check
        if made is None:
            made, insides = self._made(value, access, place, check)
        elif access is None or id(value) in self._named or id(value) in self._whole:
            return made
        else:
            insides = self._takes(value, made, check)
        if insides is None:
            return made
        if access is not None:
            self._named.add(id(value))
        if form:
            self._forms.add(id(made))
            self._later(form_items(cast(dict[object, object], insides), access, cast(Any, made)))
        else:
            self._later(_insides(value, insides, access, made, check))
        return made

    def _form(self, value: object, made: object, place: Place) -> bool:
        """Whether ``value`` is an object form the walk keeps the shape of (``form_items``).

        That is one at a parameter's own value, but not the dict a method's
        instance is built from, which takes ``Fields``, and one a holder of
        fixed shape holds: the fields of a built instance, an object form, or
        its ``"__args__"``. In any other place such a dict stays a dict.
        """
        if made is not None:
            return id(made) in self._forms
        if not object_form(value):
            return False
        if id(place.into) in self._fixed:
            return True
        return isinstance(place.access, str) and not isinstance(place.check, Fields)

    def _made(
        self, value: object, access: Expression | None, place: Place, check: Check | None
    ) -> tuple[object, _Insides | None]:
        """A container's or an object's copy, made the first time the walk reaches it, and what
        it takes; None for a copy handed on as it is. A list or a dict under ``Fields``, or one
        that holds an object form (``holding_forms``), is a plain copy of fixed shape, and its
        own annotation still reads its items."""
        if type(value) is not list and type(value) is not dict:
            made = self._copy_followed(value)
            return made, None if id(value) in self._whole else self._takes(value, made, check)
        items: list[object] | dict[object, object]
        fixed = isinstance(check, Fields) or id(value) in self._holding
        if isinstance(value, list) and access is not None and not fixed:
            made, items = self._visitor.listed(value, place)
            self._tracked.add(id(made))
        elif isinstance(value, list):
            made, items = [None] * len(value), list(value)
        elif access is not None and not fixed:
            made, items = self._visitor.mapped(keyed(value, check), place)
        else:
            # a dict under no access, or under ``Fields``: a plain copy, its keys and length fixed
            items = keyed(value, check)
            made = dict.fromkeys(items)
        if fixed:
            self._fixed.add(id(made))
        self._copies[id(value)] = made
        self._kept.append(value)
        return made, items

    def _visit_tuple(
        self, value: tuple[object, ...], access: Expression | None, place: Place
    ) -> Later:
        """Note where a tuple goes, and queue its items the first time the walk reaches it, and
        again, named, when a path that names it reaches one first reached under no name."""
        build = self._tuples.get(id(value))
        if build is None:
            build = self._tuples[id(value)] = TupleBuild(value)
            self._kept.append(value)
        if not build.visiting and (not build.visited or (access is not None and not build.named)):
            self._queue_items(build, access)
        build.placements.append((place.into, place.slot))
        return Later.VALUE

    def _queue_items(self, build: TupleBuild, access: Expression | None) -> None:
        """Queue a tuple's items into a list of their own, and the tuple before them, so the
        stack pops it after every value under them: until then it is reached inside itself."""
        build.visited, build.visiting, build.named = True, True, access is not None
        items: list[object] = [None] * len(build.value)
        build.items = items
        self._owners[id(items)] = build
        self._kept.append(items)
        self._pending.append(build)
        self._later(
            (item, step(access, at), items, at, None) for at, item in enumerate(build.value)
        )

    def _copy_later(self, value: object, place: Place) -> Later:
        """Note where a value the walk does not follow goes: it is copied whole once every path
        is walked."""
        self._to_copy.append((value, place.into, place.slot))
        self._kept.append(value)
        return Later.VALUE

    def _finish(self) -> None:
        """Once every path is walked, build each tuple and copy each value the walk does not
        follow whole, and put each everywhere the walk put it, in a fixed order.

        First the tuples whose items hold no value copied whole, themselves
        or through a tuple inside, innermost first; then the values copied
        whole that sit among the other tuples' items; then those tuples; then
        every other value copied whole. So a copy made whole outside a tuple's
        items that hashes an object the walk copied hashes it with its tuples
        in place, and a tuple that holds a value copied whole holds it once it
        is built. Each value
        is copied whole by deepcopy over the walk's copies and the copies made
        before it, so it holds the walk's copy of each object, list and dict
        the walk copied, whatever the seed's order; an object only it reaches
        is deepcopy's own copy, and nothing else it holds is tracked. A tuple
        inside it is a copy of its own.
        """
        builds = list(self._tuples.values())
        order = innermost_first(builds, tuples_among(builds, self._owners))
        placements = [(into, slot) for _, into, slot in self._to_copy]
        waiting = holding(order, placements, self._owners)
        inside: list[tuple[object, Holder, Slot]] = []
        outside: list[tuple[object, Holder, Slot]] = []
        for each in self._to_copy:
            (inside if among_items(each[1], self._owners) else outside).append(each)
        memo: dict[int, object] = dict(self._copies)
        for build in order:
            if id(build) not in waiting:
                _build(build)
        self._copy_whole(inside, memo)
        for build in order:
            if id(build) in waiting:
                _build(build)
        self._copy_whole(outside, memo)

    def _copy_whole(
        self, values: list[tuple[object, Holder, Slot]], memo: dict[int, object]
    ) -> None:
        """Copy each value the walk does not follow whole, in walk order, and put it where it
        goes.

        deepcopy records a copy before it fills it, so each copies into a
        scratch memo over ``memo``, and only a copy that finishes joins it;
        one it refuses goes on as it came.
        """
        for value, into, slot in values:
            scratch = Scratch(memo)
            try:
                made = copy.deepcopy(value, scratch)
            except Exception:
                made = value
            else:
                self._kept.extend(scratch.pop(id(scratch), []))
                memo.update(scratch)
            put(into, slot, made, value)

    def _copy_followed(self, value: object) -> object:
        """An object's copy, made by one deepcopy over the walk's copies, or the object itself
        when deepcopy refuses it, a lock say.

        deepcopy runs any ``__deepcopy__`` or pickling hook a value brings.
        It records a copy before it fills it, so it copies into a scratch
        memo, and only copies the walk may go into join the walk's, once the
        copy finishes (``copies.faithful_copies``): a refused copy leaves no
        half-made copy behind. An object whose own copy may not be gone into
        is handed on as deepcopy made it, with nothing under it joined.
        """
        scratch = Scratch(self._copies)
        try:
            copied = copy.deepcopy(value, scratch)
        except Exception:
            self._whole.add(id(value))
            self._kept.append(value)
            return value
        # deepcopy keeps what it copied alive in a list under the memo's own identity, which the
        # scratch memo gives up when it goes, so the walk keeps them instead
        self._kept.extend(scratch.pop(id(scratch), []))
        joined = faithful_copies(value, scratch)
        self._copies[id(value)] = copied
        self._kept.append(value)
        if joined is None:
            self._whole.add(id(value))
        else:
            self._copies.update(joined.copies)
            self._keys.update(joined.keys)
        return copied

    def _takes(self, value: object, made: object, check: Check | None) -> _Insides:
        """What a value takes from the walk into its copy: a list's items, a dict's, or an
        object's attributes.

        Each copy of a subclass or an object the walk reaches here passed
        ``copies.faithful_copies`` when it was made. A dict subclass's items
        are read with ``dict``'s own methods, each paired with its key by
        identity, in the order its copy holds its keys, so no subclass's code
        runs.
        """
        if isinstance(value, list):
            return list(list.__iter__(value))
        if type(value) is not dict and isinstance(value, dict):
            by_key = {id(key): item for key, item in dict.items(value)}
            return keyed({key: by_key[id(key)] for key in self._keys[id(value)]}, check)
        if isinstance(value, dict):
            return keyed(value, check)
        return objects.attributes(value, made)


def _build(build: TupleBuild) -> None:
    """Build a tuple from the items its last visit placed, with ``tuple.__new__`` so a
    namedtuple's own constructor does not run, and put it everywhere the walk put it."""
    made = tuple.__new__(type(build.value), build.items)
    for into, slot in build.placements:
        put(into, slot, made, build.value)


def _insides(
    value: object, insides: _Insides, access: Expression | None, into: object, check: Check | None
) -> Iterable[Pending]:
    """The values inside a container or an object to place into its copy, in order: a list's
    and a dict's items (see ``_items``), or an object's attributes, which take no check."""
    if isinstance(insides, Attributes):
        held = Held(into)
        return (
            (item, objects.step(access, each), held, each, None) for each, item in insides.pairs
        )
    return items_to_place(
        value, insides, access, cast(list[object] | dict[Any, object], into), check
    )
