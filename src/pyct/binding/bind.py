"""Turn a seed dict into the arguments the target is called with."""

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TypeGuard

from pyct.binding.annotations import Check, Items
from pyct.binding.shapes import ListShape, shaped
from pyct.binding.walk import Place, Walk
from pyct.core.branch import BranchSink, Expression
from pyct.core.ints import ConcolicInt
from pyct.core.list_state import kinds_of
from pyct.core.lists import ConcolicList
from pyct.core.strs import ConcolicStr


def bind(seed: Mapping[str, object], sink: BranchSink) -> dict[str, object]:
    """Give every int and str in the seed, at any depth, its access and the sink, and every
    list the walk names its form.

    A parameter's own value is named by the parameter. A value inside a dict
    or a list is named by the access that reaches it, one ``["[]", <container>,
    <key>]`` per step, so ``config["server"]["port"]`` is
    ``["[]", ["[]", "config", "'server'"], "'port'"]``. A bool is an int to
    Python but not a number to bind: it has no ``<`` worth tracking. A list the
    walk names is a tracked list whose form is its access, so its length and
    its changes are followed too.

    Every dict and list the walk reaches is rebuilt, whatever key it sits
    under, and every other value deepcopy can copy is copied, so a change the
    target makes to a copy reaches neither the seed nor a later input. A
    value under a key no access can name, a float key say, is copied the same
    way and tracked nowhere; a value deepcopy refuses is handed on as it came
    (see ``Walk``).
    """
    tracker = _Tracker(sink)
    args = Walk(tracker).rebuilt(seed)
    # each list's items are placed after the list is made, so what pyct saw of them is noted
    # once the walk is done, before the target can touch any
    for made in tracker.lists:
        made.shadow = made.storage()
        made.kinds = kinds_of(made.shadow)
    return args


class _Tracker:
    """bind's visitor: a tracked int or str for each value, a tracked list for each list."""

    def __init__(self, sink: BranchSink) -> None:
        self.sink = sink
        self.lists: list[ConcolicList] = []

    def scalar(self, value: int | str, place: Place) -> object:
        if isinstance(value, str):
            return ConcolicStr(value, expression=place.access, sink=self.sink)
        return ConcolicInt(value, expression=place.access, sink=self.sink)

    def listed(self, value: list[object], place: Place) -> tuple[list[object], list[object]]:
        made = ConcolicList.made([None] * len(value), place.access, self.sink)
        self.lists.append(made)
        return made, list(value)


@dataclass(frozen=True)
class Seed:
    """An input's arguments as the walk copied them, and what the solver may answer about.

    ``leaves`` names each int and str the solver declares on its own: a parameter, or a value
    inside a dict. ``lists`` names each tracked list the solver declares as a length and its
    items, with its shape; an int or a str inside one is an item of it, not a leaf. ``checks``
    is what each parameter's annotation asks of it, which says the kind of an item the solver
    adds to a list with none to go by, for this input and each answer made from it. The target
    is never called with the dicts and lists here: ``bind`` rebuilds them for each call. So
    they stay as the walk made them, and every solve and every answer on the input's path reads
    them rather than walking the input again.
    """

    args: Mapping[str, object]
    leaves: Mapping[str, type]
    lists: Mapping[str, ListShape] = field(default_factory=dict)
    checks: Mapping[str, Check] = field(default_factory=dict)
    # each leaf's value in this input, which settles how a list the path changed was cut
    values: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def of(cls, args: Mapping[str, object], checks: Mapping[str, Check] | None = None) -> "Seed":
        """The arguments copied, and their leaves and lists noted, in one walk."""
        noted = Noted()
        copied = Walk(noted).rebuilt(args, checks)
        return cls(copied, noted.leaves, noted.shapes(), checks or {}, noted.values)


class Noted:
    """Seed's visitor: each leaf and list noted by name, each list's shape made after the walk."""

    def __init__(self) -> None:
        # every int and str in walk order, and those the solver declares on their own
        self.named: dict[str, type] = {}
        self.leaves: dict[str, type] = {}
        self.values: dict[str, object] = {}
        # each tracked list in the order the walk made it: its copy, its name or the list and
        # position it is a row of, and what its annotation asks of each item
        self.made: list[tuple[list[object], str | tuple[int, int], Check | None]] = []

    def scalar(self, value: int | str, place: Place) -> object:
        return self.noted(value, place)

    def noted(self, value: object, place: Place) -> object:
        """Note a tracked value by its name and type, and hand it back to go where it was."""
        name = leaf_name(place.access)
        self.named[name] = type(value)
        if not place.in_list:
            self.leaves[name] = type(value)
            self.values[name] = value
        return value

    def listed(self, value: list[object], place: Place) -> tuple[list[object], list[object]]:
        made: list[object] = [None] * len(value)
        where = (id(place.into), place.slot) if place.in_list else leaf_name(place.access)
        check = place.check
        each = check.each if isinstance(check, Items) and check.kind is list else None
        self.made.append((made, where, each))
        return made, list(value)

    def shapes(self) -> dict[str, ListShape]:
        """Each list's shape, its rows first: the walk made every row after its list."""
        rows: dict[int, dict[int, ListShape]] = {}
        named: dict[str, ListShape] = {}
        for made, where, each in reversed(self.made):
            shape = shaped(made, rows.pop(id(made), {}), each)
            if isinstance(where, str):
                named[where] = shape
            else:
                rows.setdefault(where[0], {})[where[1]] = shape
        return dict(reversed(named.items()))


def leaves(seed: Mapping[str, object]) -> dict[str, type]:
    """The name and type of every int and str ``bind`` tracks, in the seed's order.

    Each is named as ``leaf_name`` names it: the leaves the solver declares and the items of
    the lists it declares, every value a fork can name by its access.
    """
    noted = Noted()
    Walk(noted).rebuilt(seed)
    return noted.named


# the head of each step an access takes to a value inside an argument: `["[]", container, key]`
_STEPS = frozenset({"[]"})


def access_name(part: Expression) -> str | None:
    """The leaf name of a part of a condition that reads as an access, or None for any other.

    Only a chain of the steps the walk takes, each key not a list, down to a
    str can be an access, so only such a chain is written out as JSON to be
    looked up. The chain is read in a loop first, so a part
    that holds a long or shared expression costs a step or two, not the
    expression written out. Whether the seed holds that access is the
    caller's to ask.
    """
    step: Expression = part
    while _is_step(step):
        step = step[1]
    if step is part or not isinstance(step, str):
        return None
    return leaf_name(part)


def _is_step(part: Expression) -> TypeGuard[list[Expression]]:
    """Whether a part is one step of an access, ``["[]", <container>, <key>]``, its key no list."""
    return (
        isinstance(part, list)
        and len(part) == 3
        and isinstance(part[0], str)
        and part[0] in _STEPS
        and not isinstance(part[2], list)
    )


def leaf_name(access: Expression) -> str:
    """The name a tracked value goes by in a model: its parameter's, or its access as JSON.

    An access's JSON opens with a bracket, so it never shares a name with a
    parameter whose name is an identifier.
    """
    return access if isinstance(access, str) else json.dumps(access)
