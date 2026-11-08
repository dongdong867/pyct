"""One walk of a seed: every dict and list rebuilt, every object's attributes followed, and every
value bind tracks handed to a visitor.

bind, the seed's leaves and the model all read this one walk, so they cannot disagree about
which values are tracked, what each is named, or which lists and dicts are tracked whole.
"""

from __future__ import annotations

import copy
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol, TypeGuard

from pyct.binding import objects
from pyct.binding.annotations import Check, Fields, Items, int_keys, reads_as_int
from pyct.binding.objects import Attribute
from pyct.core.foundation.branch import Expression


@dataclass(frozen=True)
class Place:
    """Where the walk puts a value: its access, the copy it goes in and its slot there, what
    its annotation asks of it, and whether that copy is a tracked list. The copy is a dict, a
    list, or an object whose slot is an ``Attribute``."""

    access: Expression
    into: Any
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


def binds(value: object, access: Expression) -> TypeGuard[int | float | str]:
    """Whether bind tracks this value at this access: the one rule the walk reads.

    An int, a str, a float and a bool are tracked at any access. A float subclass is tracked
    as an argument's own value, and one inside a dict or a list passes through plain: no sort
    declares a value that may be anything else as well.
    """
    if isinstance(value, float) and type(value) is not float:
        return isinstance(access, str)
    return isinstance(value, int | float | str)


# the types whose values the walk hands on as they are: nothing can change one
_ATOMIC: frozenset[type] = frozenset({int, float, str, bool, type(None)})

# one value still to place: the value, and where it goes. The access is None under a key no
# access can name. The slot is an index for a list, for a dict the copy's own key, and for an
# object an ``Attribute``
type _Pending = tuple[object, Expression | None, Any, Any, Check | None]


class Walk:
    """One walk of a seed, in seed order, depth first, and never recursive.

    A list of what is left to place stands in for Python's call stack, so a
    seed nested past Python's recursion limit is walked like any other. Each
    dict and list the walk rebuilds is remembered by the identity of the
    seed's own, so one reached again, by a second path or from inside
    itself, is the same copy. Its values are named by the first path in seed
    order that names anything: a copy first reached under a key no access
    can name is walked again, into the same copy, when a path that names it
    reaches it. Each container is walked at most twice, so the walk ends.

    A list first reached under a name is tracked whole: the visitor makes its
    copy and says which items it takes, and every value placed in it is a
    value inside a tracked list. An object is copied by ``copy.deepcopy``, and
    its attributes are then followed into that copy as a dict's values are
    (see ``objects``), so the objects inside it are its copies from that one
    deepcopy, joined to the walk's own. Any other value is copied by deepcopy
    with a memo that reads the walk's copies, so a list reached through a
    tuple, say, is the walk's copy of it there too. A value deepcopy cannot
    copy stays as it came.
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
        self._pending: list[_Pending] = []

    def rebuilt(
        self, seed: Mapping[str, object], checks: Mapping[str, Check] | None = None
    ) -> dict[str, object]:
        """The seed as the walk rebuilds it, one parameter per key, each with its annotation's
        check when ``checks`` names one."""
        asked = checks or {}
        rebuilt: dict[str, object] = dict.fromkeys(seed)
        self._later((value, name, rebuilt, name, asked.get(name)) for name, value in seed.items())
        while self._pending:
            value, access, into, slot, check = self._pending.pop()
            in_list = id(into) in self._tracked
            placed = self._placed(value, access, Place(access, into, slot, check, in_list))
            _put(into, slot, placed, value)
        return rebuilt

    def _later(self, values: Iterable[_Pending]) -> None:
        """Queue values to place in the order given: the stack pops the last one first."""
        self._pending.extend(reversed(list(values)))

    def _placed(self, value: object, access: Expression | None, place: Place) -> object:
        """What goes where ``value`` was: its tracked form, its copy, or the value itself.

        A dict and a list, and not their subclasses, are copied, and their
        values queued, and so are an object's attributes. A value with no
        access is never tracked, and neither is anything under it.
        """
        if access is not None and binds(value, access):
            return self._visitor.scalar(value, place)
        if type(value) in _ATOMIC:
            return value
        if type(value) is not list and type(value) is not dict and not objects.followed(value):
            return self._deep_copy(value)
        made = self._copies.get(id(value))
        if made is None:
            made, items = self._made(value, access, place)
            if made is value:
                # an object that copies as itself, or cannot be copied
                return value
        elif access is None or id(value) in self._named:
            return made
        else:
            items = _again(value, place.check)
        if access is not None:
            self._named.add(id(value))
        self._later(_insides(value, items, access, made, place.check))
        return made

    def _made(self, value: object, access: Expression | None, place: Place) -> tuple[Any, Any]:
        """A container's or an object's copy, made the first time the walk reaches it, and what
        it takes: an object's are its attributes, read once it is queued."""
        if not isinstance(value, list | dict):
            return self._deep_copy(value, _not_rebuilt), None
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

    def _deep_copy(self, value: object, joins: Callable[[object], bool] = lambda _: True) -> object:
        """A copy of a value the walk does not rebuild, or the value itself when it has none.

        deepcopy runs any ``__deepcopy__`` or pickling hook a value brings,
        and one may refuse, a lock say: that value reaches the target as it
        came. deepcopy records a copy before it fills it, so it copies into a
        scratch memo over the walk's own, and only a copy that finishes joins
        the walk's: a refused one leaves no half-made copy behind. Of those,
        only the copies ``joins`` takes join.
        """
        scratch = _Scratch(self._copies)
        try:
            copied = copy.deepcopy(value, scratch)
        except Exception:
            return value
        # deepcopy keeps what it copied alive in a list under the memo's own identity, which the
        # scratch memo gives up when it goes, so the walk keeps them instead
        self._kept.extend(scratch.pop(id(scratch), []))
        self._copies.update((key, made) for key, made in scratch.items() if joins(made))
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


def _not_rebuilt(made: object) -> bool:
    """Whether a copy an object's deepcopy made joins the walk's: any but a dict's and a list's,
    which the walk makes its own of when it reaches them, so they are tracked there."""
    return type(made) is not list and type(made) is not dict


def _put(into: Any, slot: Any, placed: object, value: object) -> None:
    """Put a placed value in its copy. An attribute the walk hands on as it came keeps what
    deepcopy made of it, which a class's own copy hook may have made apart from the original."""
    if isinstance(slot, Attribute):
        if placed is not value:
            slot.write(into, placed)
    elif isinstance(into, list):
        list.__setitem__(into, slot, placed)
    else:
        dict.__setitem__(into, slot, placed)


def _again(value: object, check: Check | None) -> Any:
    """What a container the walk copied takes when a path that names it reaches it again: a
    list's items and a dict's; an object's attributes are read as they are queued."""
    if isinstance(value, list):
        return list(value)
    return keyed(value, check) if isinstance(value, dict) else None


def _insides(
    value: object, items: Any, access: Expression | None, into: Any, check: Check | None
) -> Iterable[_Pending]:
    """The values inside a container or an object to place into its copy, in order: a list's
    and a dict's items (see ``_items``), or an object's attributes, which take no check."""
    if isinstance(value, list | dict):
        return _items(value, items, access, into, check)
    pairs = objects.attributes(value, into)
    return ((item, objects.step(access, each), into, each, None) for each, item in pairs)


def _items(
    value: list[object] | dict[object, object],
    items: Any,
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
    if isinstance(value, list):
        return ((item, _step(access, i), into, i, each) for i, item in enumerate(items))
    pairs = zip(dict.items(items), dict.keys(into), strict=True)
    fields = check.each if isinstance(check, Fields) else {}
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
