"""Turn a seed dict into the arguments the target is called with."""

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
    under, so the target gets a copy of its own: a change it makes to one
    reaches neither the seed nor a later input. A value under a key no access
    can name, a float key say, is copied the same way and tracked nowhere.
    Every other value, a subclass of dict or list too, passes through as it
    came.
    """
    return walked(seed, lambda value, access: _tracked(value, access, sink))


@dataclass(frozen=True)
class Seed:
    """A run's seed and the values bind tracks in it, walked for once per run.

    The seed never changes during a run, so neither do its leaves: every
    solve and every answer reads these rather than walking the seed again.
    """

    args: Mapping[str, object]
    leaves: Mapping[str, type]

    @classmethod
    def of(cls, args: Mapping[str, object]) -> "Seed":
        return cls(args=args, leaves=leaves(args))


def leaves(seed: Mapping[str, object]) -> dict[str, type]:
    """The name and type of every value ``bind`` tracks, in the seed's order.

    This is what the solver is allowed to answer about: nothing else in the
    seed carries a condition back. Each is named as ``leaf_name`` names it.
    """
    found: dict[str, type] = {}

    def note(value: int | str, access: Expression) -> object:
        found[leaf_name(access)] = type(value)
        return value

    walked(seed, note)
    return found


def leaf_name(access: Expression) -> str:
    """The name a tracked value goes by in a model: its parameter's, or its access as JSON.

    A parameter's name is an identifier and an access's JSON opens with a
    bracket, so no two tracked values share a name.
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
    itself, is the same copy and is not walked twice: its values are named
    by the first path in seed order.
    """

    def __init__(self, at_leaf: AtLeaf) -> None:
        self._at_leaf = at_leaf
        # the seed's container, kept alive beside its copy so its identity is not reused
        self._copies: dict[int, tuple[object, object]] = {}
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
        if type(value) is not list and type(value) is not dict:
            return value
        known = self._copies.get(id(value))
        if known is not None:
            return known[1]
        if isinstance(value, list):
            items: list[object] = [None] * len(value)
            self._copies[id(value)] = (value, items)
            self._later((item, _step(access, i), items, i) for i, item in enumerate(value))
            return items
        return self._copied_dict(value, access)

    def _copied_dict(self, value: dict[object, object], access: Expression | None) -> object:
        """A dict's copy, keys in the seed's order, with each value queued to place.

        A value is named by its key when the key can be written as a literal
        (see ``_key``), and by nothing otherwise.
        """
        entries: dict[object, object] = dict.fromkeys(value)
        self._copies[id(value)] = (value, entries)
        self._later((item, _step(access, _key(key)), entries, key) for key, item in value.items())
        return entries


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
