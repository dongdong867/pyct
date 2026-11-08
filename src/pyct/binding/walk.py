"""One walk of a seed: every dict, list and tuple rebuilt, every object's attributes followed,
and every value bind tracks handed to a visitor.

bind, the seed's leaves and the model all read this one walk, so they cannot disagree about
which values are tracked, what each is named, or which lists and dicts are tracked whole.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, TypeGuard

from pyct.binding import objects
from pyct.binding.annotations import Check, Fields, Items, int_keys, reads_as_int
from pyct.binding.objects import Attributes, Held
from pyct.core.foundation.branch import Expression

# where the walk puts a value: a dict's copy, a list's, the list a tuple's items are placed in
# before the tuple is built, or an object's copy
type Holder = dict[Any, object] | list[object] | Held


@dataclass(frozen=True)
class Place:
    """Where the walk puts a value: its access, the holder it goes in and its slot there, what
    its annotation asks of it, and whether that holder is a tracked list. The slot is an index
    for a list, for a dict the copy's own key, and for an object an ``Attribute``."""

    access: Expression
    into: Holder
    slot: Any
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

# one value still to place: the value, its access, and where it goes. The access is None under
# a key no access can name
type _Pending = tuple[object, Expression | None, Holder, Any, Check | None]

# what a container or an object takes from the walk into its copy: a list's items, a dict's,
# or an object's attributes
type _Insides = list[object] | dict[object, object] | Attributes


@dataclass(eq=False)
class _Tuple:
    """One tuple of the seed as the walk builds it.

    ``items`` is the list its items are placed in, for the build under way or the last one,
    and ``made`` the copy that build made. ``placements`` is every place the walk put the
    tuple, each written again when a build makes a new copy. ``named`` says the last build
    named its items.
    """

    value: tuple[object, ...]
    named: bool = False
    building: bool = False
    items: list[object] = field(default_factory=list)
    made: tuple[object, ...] | None = None
    placements: list[tuple[Holder, Any]] = field(default_factory=list)


class Walk:
    """One walk of a seed, in seed order, depth first, and never recursive.

    A list of what is left to place stands in for Python's call stack, so a
    seed of dicts, lists and tuples nested past Python's recursion limit is
    walked like any other; an object is copied by ``copy.deepcopy``, which
    recurses, so a chain of objects that deep is refused and stays as it
    came. Each dict, list and tuple the walk rebuilds, and each object it
    copies, is remembered by the identity of the seed's own, so one reached
    again, by a second path or from inside itself, is the same copy. Its
    values are named by the first path in seed order that names anything: a
    copy first reached under a key no access can name is walked again when a
    path that names it reaches it, into the same copy, or for a tuple into a
    new one that every place holding the first then holds. Each is walked at
    most twice, so the walk ends.

    A list first reached under a name is tracked whole: the visitor makes its
    copy and says which items it takes, and every value placed in it is a
    value inside a tracked list. A tuple's items are placed by index in a
    list of their own, and the tuple is built from them after, of its own
    type; one Python cannot build that way is copied whole by deepcopy, its
    values plain. An object, a subclass of dict or list among them, is copied
    by deepcopy with a memo that reads the walk's copies, and its attributes,
    or its items, are then followed into that copy (see ``objects``), so the
    objects inside it are its copies from that one deepcopy, joined to the
    walk's own. A value deepcopy cannot copy stays as it came, and so does an
    object it copies as itself; a copy of another type or length than its
    original is handed on as deepcopy made it.
    """

    def __init__(self, visitor: Visitor) -> None:
        self._visitor = visitor
        # each copy by the identity of the seed's value, which is kept alive beside it so its
        # identity is not reused, the containers whose copies a path names, and the copies
        # that are tracked lists. The copies are what deepcopy finds before it copies a value
        self._copies: dict[int, Any] = {}
        self._kept: list[object] = []
        self._named: set[int] = set()
        self._tracked: set[int] = set()
        # each tuple by the identity of the seed's, and by the identity of each list its items
        # were placed in
        self._tuples: dict[int, _Tuple] = {}
        self._scratches: dict[int, _Tuple] = {}
        self._pending: list[_Pending | _Tuple] = []

    def rebuilt(
        self, seed: Mapping[str, object], checks: Mapping[str, Check] | None = None
    ) -> dict[str, object]:
        """The seed as the walk rebuilds it, one parameter per key, each with its annotation's
        check when ``checks`` names one."""
        asked = checks or {}
        rebuilt: dict[str, object] = dict.fromkeys(seed)
        self._later((value, name, rebuilt, name, asked.get(name)) for name, value in seed.items())
        while self._pending:
            entry = self._pending.pop()
            if isinstance(entry, _Tuple):
                self._build(entry)
                continue
            value, access, into, slot, check = entry
            in_list = id(into) in self._tracked
            placed = self._placed(value, access, Place(access, into, slot, check, in_list))
            _put(into, slot, placed, value)
        return rebuilt

    def _later(self, values: Iterable[_Pending]) -> None:
        """Queue values to place in the order given: the stack pops the last one first."""
        self._pending.extend(reversed(list(values)))

    def _placed(self, value: object, access: Expression | None, place: Place) -> object:
        """What goes where ``value`` was: its tracked form, its copy, or the value itself. A
        value with no access is never tracked, and neither is anything under it."""
        if access is not None and binds(value, access):
            return self._visitor.scalar(value, place)
        if type(value) in _ATOMIC:
            return value
        if isinstance(value, tuple):
            return self._tuple(value, access, place)
        if not objects.followed(value):
            return self._deep_copy(value)
        return self._followed(value, access, place)

    def _followed(self, value: object, access: Expression | None, place: Place) -> object:
        """A dict's, a list's or an object's copy, its items or attributes queued.

        A dict and a list are copied, and their values queued, and so are an
        object's attributes, or its items for a subclass of dict or list.
        """
        made = self._copies.get(id(value))
        if made is None:
            made, insides = self._made(value, access, place)
        elif access is None or id(value) in self._named:
            return made
        else:
            insides = _again(value, made, place.check)
        if insides is None:
            return made
        if access is not None:
            self._named.add(id(value))
        self._later(_insides(value, insides, access, made, place.check))
        return made

    def _made(
        self, value: object, access: Expression | None, place: Place
    ) -> tuple[Any, _Insides | None]:
        """A container's or an object's copy, made the first time the walk reaches it, and what
        it takes; None for one handed on as it is (see ``_again``)."""
        if type(value) is not list and type(value) is not dict:
            made = self._deep_copy(value)
            return made, _again(value, made, place.check)
        if isinstance(value, list) and access is not None:
            made, items = self._visitor.listed(value, place)
            self._tracked.add(id(made))
        elif isinstance(value, list):
            made, items = [None] * len(value), list(value)
        elif access is not None and not isinstance(place.check, Fields):
            made, items = self._visitor.mapped(keyed(value, place.check), place)
        else:
            # a dict under no access, or under ``Fields``: a plain copy, its keys and length fixed
            items = keyed(value, place.check)
            made = dict.fromkeys(items)
        self._copies[id(value)] = made
        self._kept.append(value)
        return made, items

    def _tuple(self, value: tuple[object, ...], access: Expression | None, place: Place) -> object:
        """A tuple's copy, or None while its first build is under way (see ``_build``).

        A tuple is built again, its items named, when a path that names it
        reaches one built under no name. A tuple reached inside itself,
        through a list, a dict or an object, gets the copy its build makes.
        """
        state = self._tuples.get(id(value))
        if state is None:
            made = self._copies.get(id(value))
            if made is not None or not _buildable(value):
                return made if made is not None else self._deep_copy(value)
            state = self._tuples[id(value)] = _Tuple(value)
            self._kept.append(value)
        if not state.building and (state.made is None or (access is not None and not state.named)):
            self._start(state, access)
        state.placements.append((place.into, place.slot))
        return state.made

    def _start(self, state: _Tuple, access: Expression | None) -> None:
        """Start a build of a tuple: its items queued into a list of their own, and the tuple
        queued before them, so the stack pops it after every value under them."""
        state.building, state.named = True, access is not None
        items: list[object] = [None] * len(state.value)
        state.items = items
        self._scratches[id(items)] = state
        self._kept.append(items)
        self._pending.append(state)
        self._later(
            (item, _step(access, at), items, at, None) for at, item in enumerate(state.value)
        )

    def _build(self, state: _Tuple) -> None:
        """Build a tuple whose items are placed, and write it everywhere the walk put it.

        ``tuple.__new__`` builds it, so a namedtuple's own constructor does
        not run. A place that is the item list of a tuple already built makes
        that tuple be built again, so each holds the other's latest copy.
        """
        state.building = False
        settled = [(state, tuple.__new__(type(state.value), state.items))]
        while settled:
            each, made = settled.pop()
            each.made = made
            self._copies[id(each.value)] = made
            for into, slot in each.placements:
                _put(into, slot, made, each.value)
                owner = self._scratches.get(id(into))
                if owner is not None and into is owner.items and not owner.building:
                    settled.append((owner, tuple.__new__(type(owner.value), owner.items)))

    def _deep_copy(self, value: object) -> object:
        """A copy of a value the walk does not rebuild, or the value itself when it has none.

        deepcopy runs any ``__deepcopy__`` or pickling hook a value brings,
        and one may refuse, a lock say: that value reaches the target as it
        came. deepcopy records a copy before it fills it, so it copies into a
        scratch memo over the walk's own, and only a copy that finishes joins
        the walk's: a refused one leaves no half-made copy behind. Of the
        copies made inside the value, a dict's, a list's and a tuple's stay
        out, so the walk makes its own of each when it reaches it, whatever
        path reaches it first.
        """
        scratch = _Scratch(self._copies)
        try:
            copied = copy.deepcopy(value, scratch)
        except Exception:
            return value
        # deepcopy keeps what it copied alive in a list under the memo's own identity, which the
        # scratch memo gives up when it goes, so the walk keeps them instead
        self._kept.extend(scratch.pop(id(scratch), []))
        self._copies.update((key, made) for key, made in scratch.items() if _joins(made))
        if copied is not value:
            self._copies[id(value)] = copied
            self._kept.append(value)
        return copied


class _Scratch(dict[int, Any]):
    """deepcopy's memo for one copy: what it copies now, read over what the walk already has.

    deepcopy looks a value up with ``get``, and a tuple's copy with an
    index, and records each copy by setting it. So this dict holds only the
    new copies, and the walk's stay as they were until the copy finishes.
    """

    def __init__(self, under: Mapping[int, Any]) -> None:
        super().__init__()
        self._under = under

    def get(self, key: int, default: Any = None) -> Any:
        return super().get(key, self._under.get(key, default))

    def __missing__(self, key: int) -> Any:
        return self._under[key]


def _joins(made: object) -> bool:
    """Whether a copy deepcopy made inside a value joins the walk's: any but a dict's, a list's
    and a tuple's, which the walk makes its own of when it reaches them, so what they hold is
    followed there."""
    return type(made) is not list and type(made) is not dict and not isinstance(made, tuple)


def _buildable(value: tuple[object, ...]) -> bool:
    """Whether ``tuple.__new__`` builds a tuple of this one's type that loses nothing of it: a
    tuple, or a subclass with no ``__dict__``, a namedtuple say, that it builds; a struct
    sequence such as ``time.struct_time`` refuses."""
    kind = type(value)
    if kind is tuple:
        return True
    if kind.__dictoffset__ != 0:
        return False
    try:
        tuple.__new__(kind, ())
    except TypeError:
        return False
    return True


def _put(into: Holder, slot: Any, placed: object, value: object) -> None:
    """Put a placed value in its holder. An attribute the walk hands on as it came keeps what
    deepcopy made of it, which a class's own copy hook may have made apart from the original."""
    if isinstance(into, Held):
        if placed is not value:
            slot.write(into.made, placed)
    elif isinstance(into, list):
        list.__setitem__(into, slot, placed)
    else:
        dict.__setitem__(into, slot, placed)


def _again(value: object, made: object, check: Check | None) -> _Insides | None:
    """What a value takes from the walk into its copy: a list's items, a dict's, or an object's
    attributes.

    None for a copy that is the value itself, or one of another type, or of another length for
    a subclass of dict or list, as a class's own copy hook may make: that copy is handed on as
    deepcopy made it.
    """
    if type(value) is list:
        return list(value)
    if type(value) is dict:
        return keyed(value, check)
    if made is value or type(made) is not type(value):
        return None
    if isinstance(value, list) and isinstance(made, list):
        return list(value) if list.__len__(made) == list.__len__(value) else None
    if isinstance(value, dict) and isinstance(made, dict):
        return keyed(value, check) if dict.__len__(made) == dict.__len__(value) else None
    return objects.attributes(value, made)


def _insides(
    value: object, insides: _Insides, access: Expression | None, into: Any, check: Check | None
) -> Iterable[_Pending]:
    """The values inside a container or an object to place into its copy, in order: a list's
    and a dict's items (see ``_items``), or an object's attributes, which take no check."""
    if isinstance(insides, Attributes):
        held = Held(into)
        return (
            (item, objects.step(access, each), held, each, None) for each, item in insides.pairs
        )
    return _items(value, insides, access, into, check)


def _items(
    value: object,
    items: list[object] | dict[object, object],
    access: Expression | None,
    into: Any,
    check: Check | None,
) -> Iterable[_Pending]:
    """A container's values to place into its copy, each with the access one step in.

    A list's and a dict's are the items the walk decided it takes. A dict's value is named by
    its key when the key can be written as a literal (see ``_key``), and by nothing otherwise.
    It goes in under the copy's own key, in the same order: a copy deepcopy made holds copies
    of the seed's keys, and a key equal only to itself would go in twice. The copy's keys are
    read in C, since a tracked dict's own walk records forks. Under ``Fields``, each value takes
    its own key's check.
    """
    each = _each(check, list if isinstance(value, list) else dict)
    if isinstance(items, list):
        return ((item, _step(access, i), into, i, each) for i, item in enumerate(items))
    pairs = zip(dict.items(items), dict.keys(into), strict=True)
    fields: Mapping[Any, Check] = check.each if isinstance(check, Fields) else {}
    return (
        (item, _step(access, _key(key)), into, slot, fields.get(key, each))
        for (key, item), slot in pairs
    )


def _each(check: Check | None, kind: type) -> Check | None:
    """What a list or dict annotation asks of each of its items, when it is that kind."""
    return check.each if isinstance(check, Items) and check.kind is kind else None


def keyed(value: dict[object, object], check: Check | None) -> dict[object, object]:
    """A dict's items, each key read back as its annotation's key type says.

    JSON keys are always strings, so an int key an input's line wrote as ``"3"`` is read back
    as ``3`` under a ``dict[int, X]`` annotation, and the line's ``args`` given back through
    ``--args`` is the same input. A key written any other way, or under any other annotation,
    stays as it came.
    """
    if not int_keys(check):
        return dict(value)
    return {_read_back(key): item for key, item in dict.items(value)}


def _read_back(key: object) -> object:
    """A key as a ``dict[int, X]`` reads it: the int an int's JSON text writes, else itself."""
    return int(key) if isinstance(key, str) and reads_as_int(key) else key


class _Unnamed(Enum):
    """What ``_key`` answers for a key no access can write, apart from every literal."""

    KEY = "a key no access can name"


def _step(container: Expression | None, key: Expression | _Unnamed) -> Expression | None:
    """The access one step further in, ``["[]", container, key]``.

    None when the container has no access, or the key cannot be written.
    """
    if container is None or key is _Unnamed.KEY:
        return None
    return ["[]", container, key]


def _key(key: object) -> Expression | _Unnamed:
    """A key as an access writes it: a str in its Python quotes, an int as itself.

    Any other key is ``_Unnamed.KEY``: no access names the value under it.
    The answer is apart from every literal, so a key written as ``null`` can
    join them later.
    """
    if isinstance(key, str):
        # str's own repr: a key of the target's own str subclass may print itself another way
        return str.__repr__(key)
    if isinstance(key, int) and not isinstance(key, bool):
        return int(key)
    return _Unnamed.KEY
