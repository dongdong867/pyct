"""Turn a seed dict into the arguments the target is called with."""

import copy
import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeGuard

from pyct.core.branch import BranchSink, Expression
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr

# what a walk makes of one value bind tracks, given the access that reaches it
type AtLeaf = Callable[[int | str, Expression], object]


def bind(seed: Mapping[str, object], sink: BranchSink) -> dict[str, object]:
    """Give every int and str in the seed, at any depth, its access and the sink.

    A parameter's own value is named by the parameter. A value inside a dict
    or a list is named by the access that reaches it, one ``["[]", <container>,
    <key>]`` per step, so ``config["server"]["port"]`` is
    ``["[]", ["[]", "config", "'server'"], "'port'"]``. A bool is an int to
    Python but not a number to bind: it has no ``<`` worth tracking.

    Every dict and list the walk reaches is rebuilt, whatever key it sits
    under, and every other value deepcopy can copy is copied, so a change the
    target makes to a copy reaches neither the seed nor a later input. A
    value under a key no access can name, a float key say, is copied the same
    way and tracked nowhere; a value deepcopy refuses is handed on as it came
    (see ``_Walk``).
    """
    return walked(seed, lambda value, access: _tracked(value, access, sink))


@dataclass(frozen=True)
class Seed:
    """A run's seed as the walk copied it, and the values bind tracks in it.

    Made once, before any input runs. The target is never called with the
    dicts and lists here, which hold every leaf: ``bind`` rebuilds them for
    each call. So they and the leaves stay as the walk made them for the
    whole run, and every solve and every answer reads them rather than
    walking the caller's seed again.
    """

    args: Mapping[str, object]
    leaves: Mapping[str, type]

    @classmethod
    def of(cls, args: Mapping[str, object]) -> "Seed":
        """The seed copied, and its leaves noted, in one walk."""
        found: dict[str, type] = {}

        def note(value: int | str, access: Expression) -> object:
            found[leaf_name(access)] = type(value)
            return value

        return cls(args=walked(args, note), leaves=found)


def leaves(seed: Mapping[str, object]) -> dict[str, type]:
    """The name and type of every value ``bind`` tracks, in the seed's order.

    This is what the solver is allowed to answer about: nothing else in the
    seed carries a condition back. Each is named as ``leaf_name`` names it.
    """
    return dict(Seed.of(seed).leaves)


# the head of each step an access takes to a value inside an argument: `["[]", container, key]`
_STEPS = frozenset({"[]"})


def access_name(part: Expression) -> str | None:
    """The leaf name of a part of a condition that reads as an access, or None for any other.

    Only a list headed by one of the steps the walk takes can be an access,
    so only such a list is written out as JSON to be looked up. Whether the
    seed holds that access is the caller's to ask.
    """
    if isinstance(part, list) and part and isinstance(part[0], str) and part[0] in _STEPS:
        return leaf_name(part)
    return None


def leaf_name(access: Expression) -> str:
    """The name a tracked value goes by in a model: its parameter's, or its access as JSON.

    An access's JSON opens with a bracket, so it never shares a name with a
    parameter whose name is an identifier.
    """
    return access if isinstance(access, str) else json.dumps(access)


def walked(seed: Mapping[str, object], at_leaf: AtLeaf) -> dict[str, object]:
    """The seed rebuilt, with ``at_leaf``'s answer in place of every value bind tracks.

    bind, leaves and the model all read this one walk, so they cannot
    disagree about which values are tracked or what each is named.
    """
    return _Walk(at_leaf).rebuilt(seed)


def _binds(value: object) -> TypeGuard[int | str]:
    """Whether bind tracks this value: the one rule the walk reads."""
    return isinstance(value, int | str) and not isinstance(value, bool)


# the types whose values the walk hands on as they are: nothing can change one
_ATOMIC: frozenset[type] = frozenset({int, float, str, bool, type(None)})

# one value still to place: the value, its access, and the container and slot its copy goes in.
# The access is None under a key no access can name. The slot is an index for a list and any key
# for a dict, the seed's own
type _Pending = tuple[object, Expression | None, dict[Any, object] | list[object], Any]


class _Walk:
    """One walk of a seed, in seed order, depth first, and never recursive.

    A list of what is left to place stands in for Python's call stack, so a
    seed nested past Python's recursion limit is walked like any other. Each
    dict and list the walk rebuilds is remembered by the identity of the
    seed's own, so one reached again, by a second path or from inside
    itself, is the same copy. Its values are named by the first path in seed
    order that names anything: a copy first reached under a key no access
    can name is walked again, into the same copy, when a path that names it
    reaches it. Each container is walked at most twice, so the walk ends.

    Any other value is copied by ``copy.deepcopy`` with a memo that reads the
    walk's copies, so a list reached through a tuple, say, is the walk's copy
    of it there too. A value deepcopy cannot copy stays as it came.
    """

    def __init__(self, at_leaf: AtLeaf) -> None:
        self._at_leaf = at_leaf
        # each copy by the identity of the seed's value, which is kept alive beside it so its
        # identity is not reused, and the containers whose copies a path names. The copies are
        # what deepcopy finds before it copies a value again
        self._copies: dict[int, Any] = {}
        self._kept: list[object] = []
        self._named: set[int] = set()
        self._pending: list[_Pending] = []

    def rebuilt(self, seed: Mapping[str, object]) -> dict[str, object]:
        """The seed as the walk rebuilds it, one parameter per key."""
        rebuilt: dict[str, object] = dict.fromkeys(seed)
        self._later((value, name, rebuilt, name) for name, value in seed.items())
        while self._pending:
            value, access, into, slot = self._pending.pop()
            into[slot] = self._placed(value, access)
        return rebuilt

    def _later(self, values: Iterable[_Pending]) -> None:
        """Queue values to place in the order given: the stack pops the last one first."""
        self._pending.extend(reversed(list(values)))

    def _placed(self, value: object, access: Expression | None) -> object:
        """What goes where ``value`` was: its tracked form, its copy, or the value itself.

        A dict and a list, and not their subclasses, are copied, and their
        values queued. A value with no access is never tracked, and neither is
        anything under it.
        """
        if access is not None and _binds(value):
            return self._at_leaf(value, access)
        if type(value) in _ATOMIC:
            return value
        if type(value) is not list and type(value) is not dict:
            return self._deep_copy(value)
        made = self._copies.get(id(value))
        if made is None:
            made = [None] * len(value) if isinstance(value, list) else dict.fromkeys(value)
            self._copies[id(value)] = made
            self._kept.append(value)
        elif access is None or id(value) in self._named:
            return made
        if access is not None:
            self._named.add(id(value))
        self._later(_items(value, access, made))
        return made

    def _deep_copy(self, value: object) -> object:
        """A copy of a value the walk does not rebuild, or the value itself when it has none.

        deepcopy runs any ``__deepcopy__`` or pickling hook a value brings,
        and one may refuse, a lock say: that value reaches the target as it
        came. deepcopy records a copy before it fills it, so it copies into a
        scratch memo over the walk's own, and only a copy that finishes joins
        the walk's: a refused one leaves no half-made copy behind.
        """
        scratch = _Scratch(self._copies)
        try:
            copied = copy.deepcopy(value, scratch)
        except Exception:
            return value
        # deepcopy keeps what it copied alive in a list under the memo's own identity, which the
        # scratch memo gives up when it goes, so the walk keeps them instead
        self._kept.extend(scratch.pop(id(scratch), []))
        self._copies.update(scratch)
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


def _items(
    value: list[object] | dict[object, object], access: Expression | None, into: Any
) -> Iterable[_Pending]:
    """A container's values to place into its copy, each with the access one step in.

    A dict's value is named by its key when the key can be written as a
    literal (see ``_key``), and by nothing otherwise. It goes in under the
    copy's own key, in the same order: a copy deepcopy made holds copies of
    the seed's keys, and a key equal only to itself would go in twice.
    """
    if isinstance(value, list):
        return ((item, _step(access, i), into, i) for i, item in enumerate(value))
    pairs = zip(value.items(), into, strict=True)
    return ((item, _step(access, _key(key)), into, slot) for (key, item), slot in pairs)


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


def _tracked(value: int | str, access: Expression, sink: BranchSink) -> object:
    if isinstance(value, str):
        return ConcolicStr(value, expression=access, sink=sink)
    return ConcolicInt(value, expression=access, sink=sink)
