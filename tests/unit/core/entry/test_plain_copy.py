"""The copy of a list or dict going in that a loss site in use reads (`as_it_went_in`): a copy of
the list or dict itself, so a call that removes its items leaves the copy as it went in. A tracked
one is a tracked copy one level deep, or, when C code changed its length, a plain copy in which
each list, tuple, dict, set and frozenset, a subclass of one included, that holds a tracked value
at any depth is a plain copy too, and each tracked int, float, str or bool, a dict's keys
included, is its plain value. Taking either copy, and reading a plain one, records nothing, and
leaves the target's own as it is."""

import collections
import dataclasses
import datetime
import decimal
import enum
import fractions
import heapq
import sys
import uuid
from collections.abc import Callable, Mapping
from typing import Any, cast

import pytest

from pyct.binding.bind import bind
from pyct.core.entry.in_use import as_it_went_in
from pyct.core.foundation.branch import SinkItem
from pyct.core.lists.lists import ConcolicList

type Change = Callable[[Mapping[str, Any]], None]


def bound_and_changed(
    going_in: Mapping[str, object], change: Change
) -> tuple[dict[str, object], list[SinkItem]]:
    """The values going in, bound, after ``change`` changed them as C code does, and their sink."""
    sink: list[SinkItem] = []
    args = bind(going_in, sink)
    change(args)
    return args, sink


def copied(value: object, sink: list[SinkItem]) -> object:
    """The copy of ``value``, which records nothing."""
    before = len(sink)
    made = as_it_went_in(value)
    assert sink[before:] == []
    return made


def test_a_copy_of_a_list_the_call_empties_keeps_its_items_as_they_went_in() -> None:
    xs = [1, 2, 3]

    made = as_it_went_in(xs)
    xs.clear()

    assert made == [1, 2, 3]


def test_a_tracked_list_or_dict_going_in_reaches_the_formula_tracked_as_a_copy() -> None:
    args, sink = bound_and_changed({"xs": [1, 2], "d": {"a": 1}}, lambda _: None)

    xs, d = copied(args["xs"], sink), copied(args["d"], sink)

    assert type(xs) is ConcolicList
    assert xs is not args["xs"]
    assert cast(ConcolicList, xs).expression == cast(ConcolicList, args["xs"]).expression
    assert d is not args["d"]
    assert getattr(d, "expression", None) == getattr(args["d"], "expression", None) == "d"


def compares_the_largest(xs: Any) -> None:
    assert max(xs) > 4


def compares_a(d: Any) -> None:
    assert d["a"] > 0


def compares_the_largest_first(xs: Any) -> None:
    assert max(each[0] for each in xs) > 4


def compares_a_s_first_b(d: Any) -> None:
    assert d["a"][0]["b"] > 0


def compares_the_ints_the_first_holds(xs: Any) -> None:
    """Compare each int the list's first item holds at any depth, a dict's keys and values
    included."""
    inside = [xs[0]]
    while inside:
        each = inside.pop()
        if isinstance(each, dict):
            inside.extend([*each, *each.values()])
        elif isinstance(each, list | tuple | set | frozenset):
            inside.extend(each)
        elif isinstance(each, int):
            assert each > 4


def compares_the_keys(d: Any) -> None:
    assert all(key != "z" for key in d)


def pushed(made: Callable[[Any], object]) -> Change:
    """Push what ``made`` makes of ``p`` onto the heap ``xs``, as C code does."""
    return lambda args: heapq.heappush(args["xs"], made(args["p"]))


# what a list's first item the C code pushes holds, by what it is, made of ``p``
HELD: dict[str, Callable[[Any], object]] = {
    "Python's own lists": lambda p: [p],
    "tuples": lambda p: (p, "task"),
    "tuples of a tuple and a list": lambda p: ((p,), [p]),
    "tuples of tuples nested five deep and a tuple": lambda p: (((((p,),),),), (p,)),
    "Python's own dicts": lambda p: {p: p},
    "sets": lambda p: {p},
    "frozensets": lambda p: frozenset([p]),
    "namedtuples": lambda p: collections.namedtuple("P", "cost name")(p, "task"),
    "OrderedDicts": lambda p: collections.OrderedDict(a=p),
    "defaultdicts": lambda p: collections.defaultdict(int, a=p),
    "Counters": lambda p: collections.Counter(a=p),
    "lists of a list subclass": lambda p: type("L", (list,), {})([p]),
}
# a list or dict going in that C code changed: the values going in, the change, the name of the
# one copied, and a formula comparing what its copy holds
CHANGED_FROM_C: dict[str, tuple[dict[str, object], Change, str, Callable[[Any], None]]] = {
    "a list changed from C": (
        {"xs": [3, 5]},
        lambda args: heapq.heappush(args["xs"], 0),
        "xs",
        compares_the_largest,
    ),
    "a dict changed from C": (
        {"d": {"a": 1}},
        lambda args: dict.__setitem__(args["d"], "k", 9),
        "d",
        compares_a,
    ),
    "a list of lists changed from C": (
        {"xs": [[3], [5]]},
        lambda args: heapq.heappush(args["xs"], [0]),
        "xs",
        compares_the_largest_first,
    ),
    "a dict of a list of dicts changed from C": (
        {"d": {"a": [{"b": 1}]}},
        lambda args: dict.__setitem__(args["d"], "k", []),
        "d",
        compares_a_s_first_b,
    ),
    **{
        f"a list of {kind} changed from C": (
            {"xs": [], "p": 7},
            pushed(made),
            "xs",
            compares_the_ints_the_first_holds,
        )
        for kind, made in HELD.items()
    },
    "a dict given a tracked key from C": (
        {"d": {"a": 1}, "k": "x"},
        lambda args: dict.__setitem__(args["d"], args["k"], 9),
        "d",
        compares_the_keys,
    ),
}


def held_by(value: object) -> list[object]:
    """What a list or dict holds, read through its base type, each part itself."""
    if isinstance(value, dict):
        return [each for pair in dict.items(value) for each in pair]
    return list(list.__iter__(cast(list[object], value)))


@pytest.mark.parametrize(
    ("going_in", "change", "name"),
    [row[:3] for row in CHANGED_FROM_C.values()],
    ids=list(CHANGED_FROM_C),
)
def test_the_copy_of_a_list_or_dict_changed_from_c_leaves_the_target_s_own_alone(
    going_in: dict[str, object], change: Change, name: str
) -> None:
    args, sink = bound_and_changed(going_in, change)
    own = args[name]
    before = (type(own), held_by(own))

    made = copied(own, sink)

    assert made is not own
    assert type(made) in (list, dict)
    after = (type(own), held_by(own))
    assert after[0] is before[0]
    assert [id(each) for each in after[1]] == [id(each) for each in before[1]]


@pytest.mark.parametrize(
    ("going_in", "change", "name", "formula"),
    list(CHANGED_FROM_C.values()),
    ids=list(CHANGED_FROM_C),
)
def test_a_formula_comparing_what_such_a_copy_holds_records_nothing(
    going_in: dict[str, object], change: Change, name: str, formula: Callable[[Any], None]
) -> None:
    args, sink = bound_and_changed(going_in, change)
    made = copied(args[name], sink)
    before = len(sink)

    formula(made)

    assert sink[before:] == []


def test_the_copy_of_a_list_c_made_hold_itself_is_plain_and_holds_itself() -> None:
    args, sink = bound_and_changed({"xs": [[3]]}, lambda args: list.append(args["xs"], args["xs"]))

    xs = copied(args["xs"], sink)

    assert type(xs) is list
    inner, itself = cast(list[Any], xs)
    assert (type(inner), type(inner[0])) == (list, int)
    assert itself is xs


def test_the_copy_of_a_list_c_made_hold_a_tuple_of_itself_holds_a_tuple_of_its_copy() -> None:
    args, sink = bound_and_changed(
        {"xs": [3], "p": 7}, lambda args: list.append(args["xs"], (args["xs"], args["p"]))
    )

    xs = copied(args["xs"], sink)

    first, (itself, p) = cast(list[Any], xs)
    assert (type(xs), type(first), type(p)) == (list, int, int)
    assert itself is xs


@pytest.mark.parametrize("held", [(0, "task"), [0, ["task"]], {"k": (0,)}], ids=type)
def test_the_copy_keeps_a_container_that_holds_nothing_tracked_as_it_is(held: object) -> None:
    args, sink = bound_and_changed({"xs": []}, lambda args: heapq.heappush(args["xs"], held))

    xs = copied(args["xs"], sink)

    assert type(xs) is list
    assert cast(list[object], xs)[0] is held


def compares_the_deepest(xs: Any) -> None:
    each = xs[0]
    while isinstance(each, list):
        each = each[0]
    assert each > 0


def test_the_plain_copy_of_lists_nested_past_the_recursion_limit_reaches_the_formula() -> None:
    nested: list[Any] = [1]
    for _ in range(sys.getrecursionlimit() * 2):
        nested = [nested]
    args, sink = bound_and_changed({"xs": nested}, lambda args: list.append(args["xs"], 9))

    made = copied(args["xs"], sink)
    compares_the_deepest(made)

    assert type(made) is list
    assert sink == []


class Color(enum.Enum):
    RED = 1


class Base(enum.Enum):
    pass


class Shade(Base):
    DARK = 1


class Level(enum.IntEnum):
    LOW = 1


@dataclasses.dataclass(frozen=True)
class Point:
    x: int


class Own:
    def __hash__(self) -> int:
        return 1


COPIED: dict[str, Callable[[], object]] = {
    "an Enum member": lambda: Color.RED,
    "a member of an Enum the target derives": lambda: Shade.DARK,
    "an IntEnum member": lambda: Level.LOW,
    "a date": lambda: datetime.date(2026, 1, 1),
    "a Decimal": lambda: decimal.Decimal("1.5"),
    "a Fraction": lambda: fractions.Fraction(1, 3),
    "a UUID": lambda: uuid.UUID(int=1),
    "a tuple of an Enum member and a str": lambda: (Color.RED, "a"),
    "a tuple of two members of one Enum": lambda: (Color.RED, Color.RED),
}
KEPT: dict[str, Callable[[], object]] = {
    "a frozen dataclass instance": lambda: Point(1),
    "an object whose class defines its hash": Own,
    "a tuple of two such objects": lambda: (Own(), Own()),
}


def keyed(key: object) -> tuple[object, object, list[SinkItem]]:
    """The record a copy holds and the target's own record, for a stale heap holding
    ``{key: p}`` whose record the call then changes in place, and the sink."""
    args, sink = bound_and_changed({"xs": [], "p": 7}, pushed(lambda p: {key: p}))
    made = copied(args["xs"], sink)
    own = list.__getitem__(cast(list[object], args["xs"]), 0)
    cast(dict[object, int], own)[key] = 0
    return list.__getitem__(cast(list[object], made), 0), own, sink


@pytest.mark.parametrize("key", list(COPIED.values()), ids=list(COPIED))
def test_a_record_keyed_by_python_s_own_type_is_copied_plain(key: Callable[[], object]) -> None:
    record, own, _ = keyed(key())

    assert record is not own
    assert type(record) is dict
    assert [(type(each), each) for each in dict.values(cast(dict, record))] == [(int, 7)]


@pytest.mark.parametrize("key", list(KEPT.values()), ids=list(KEPT))
def test_a_record_keyed_by_a_hash_the_target_s_class_has_is_kept_as_it_is(
    key: Callable[[], object],
) -> None:
    record, own, _ = keyed(key())

    assert record is own
