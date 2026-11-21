"""A loop in use keeps, as it starts, a copy of each list or dict going in, of the list or dict
itself: its formula, and the record of a run it fails on, read the list or dict as it went in
after the loop removes its items. A tracked one reaches the formula as a tracked copy one level
deep, or, when its length changed from C, as a plain copy whose tracked lists and dicts inside are
plain copies too, at every depth. The plain one records what the loop as written records."""

from collections.abc import Callable, Mapping
from typing import Any, cast

import pytest

from pyct.binding.bind import bind
from pyct.core.entry.in_use import LoopInUse
from pyct.core.foundation.branch import Branch, Downgrade, Fact, GoingIn, SinkItem
from pyct.core.lists.lists import ConcolicList
from pyct.core.numbers.ints import ConcolicInt
from tests.unit.core.entry.test_in_use import drops, forks, using
from tests.unit.core.entry.test_pieces import hooked, recorded

POPS = """\
def f(xs, t):
    while xs:
        t += xs.pop()
    return t
"""
# the loop's line and column
LOOP = (2, 4)


def summed(values: Mapping[str, object]) -> Mapping[str, object]:
    """The formula of POPS's loop."""
    xs, t = values["xs"], values["t"]
    assert isinstance(xs, list)
    assert isinstance(t, int)
    return {"t": t + sum(cast(list[int], xs))}


def test_the_formula_reads_a_list_the_loop_empties_as_it_went_in() -> None:
    f = hooked(POPS)

    with using({LOOP: LoopInUse(("t", "xs"), ("t",), summed)}) as sink:
        t = cast(Any, f([1, 2, 3], ConcolicInt.made(0, expression="t", sink=sink)))

    assert drops(sink) == []
    assert type(t) is ConcolicInt
    assert (int.__int__(t), t.expression) == (6, ["+", "t", 6])


def test_a_run_past_the_first_three_whose_formula_fails_records_the_list_as_it_went_in() -> None:
    def wrong_on_two(values: Mapping[str, object]) -> Mapping[str, object]:
        xs = values["xs"]
        assert isinstance(xs, list)
        made = summed(values)["t"]
        assert isinstance(made, int)
        return {"t": made + (len(xs) > 1)}

    f = hooked(POPS)

    with using({LOOP: LoopInUse(("t", "xs"), ("t",), wrong_on_two)}) as sink:
        for xs in ([], [], [], [1, 2]):
            f(xs, 0)

    assert [each.going_in for each in recorded(sink)][-1] == (
        GoingIn("t", "0", False),
        GoingIn("xs", "[1, 2]", False),
    )
    assert [(each.value, each.got) for each in drops(sink)] == [("3", "4")]


DICT = """\
def f(xs, d, s):
    t = 0
    for c in s:
        t += 1
        g(xs, d)
    return t
"""


def test_a_tracked_list_or_dict_going_in_reaches_the_formula_tracked_as_a_copy() -> None:
    seen: list[object] = []

    def counting(values: Mapping[str, object]) -> Mapping[str, object]:
        seen.extend([values["xs"], values["d"]])
        s, t = values["s"], values["t"]
        assert isinstance(s, str)
        assert isinstance(t, int)
        return {"t": t + len(s)}

    f = hooked(DICT)
    sink: list[SinkItem]

    with using({(3, 4): LoopInUse(("d", "s", "t", "xs"), ("t",), counting)}) as sink:
        args = bind({"xs": [1, 2], "d": {"a": 1}}, sink)
        f(args["xs"], args["d"], "ab")

    xs, d = seen
    assert type(xs) is ConcolicList
    assert xs is not args["xs"]
    assert cast(ConcolicList, xs).expression == cast(ConcolicList, args["xs"]).expression
    assert d is not args["d"]
    assert getattr(d, "expression", None) == getattr(args["d"], "expression", None) == "d"
    assert (forks(sink), drops(sink)) == ([], [])


HEAP = """\
import heapq
def f(xs, s):
    heapq.heappush(xs, 0)
    t = 0
    for c in s:
        t += 1
        len(xs)
    if xs[0] > 0:
        return t
    return t
"""
STORED = """\
def f(d, s):
    dict.__setitem__(d, "k", 9)
    t = 0
    for c in s:
        t += 1
        len(d)
    if d["a"] > 0:
        return t
    return t
"""


def lengthened(values: Mapping[str, object]) -> Mapping[str, object]:
    """The formula of HEAP's and STORED's loops."""
    s, t = values["s"], values["t"]
    assert isinstance(s, str)
    assert isinstance(t, int)
    return {"t": t + len(s)}


def compares_the_largest(values: Mapping[str, object]) -> Mapping[str, object]:
    """HEAP's formula, comparing an item of the list going in."""
    xs = values["xs"]
    assert isinstance(xs, list)
    assert max(cast(list[int], xs)) > 4
    return lengthened(values)


def compares_a(values: Mapping[str, object]) -> Mapping[str, object]:
    """STORED's formula, comparing the value of the dict's key ``a``."""
    d = values["d"]
    assert isinstance(d, dict)
    assert cast(dict[str, int], d)["a"] > 0
    return lengthened(values)


HEAP_OF_LISTS = """\
import heapq
def f(xs, s):
    heapq.heappush(xs, [0])
    t = 0
    for c in s:
        t += 1
        len(xs)
    return t
"""
STORED_LISTS = """\
def f(d, s):
    dict.__setitem__(d, "k", [])
    t = 0
    for c in s:
        t += 1
        len(d)
    return t
"""


def compares_the_largest_first(values: Mapping[str, object]) -> Mapping[str, object]:
    """HEAP_OF_LISTS's formula, comparing the first item of each list in the list going in."""
    xs = values["xs"]
    assert isinstance(xs, list)
    assert max(each[0] for each in cast(list[list[int]], xs)) > 4
    return lengthened(values)


def compares_a_s_first_b(values: Mapping[str, object]) -> Mapping[str, object]:
    """STORED_LISTS's formula, comparing ``b`` in the first dict of the list at the key ``a``."""
    d = values["d"]
    assert isinstance(d, dict)
    assert cast(dict[str, list[dict[str, int]]], d)["a"][0]["b"] > 0
    return lengthened(values)


# a list or dict going in that C code changed, where its loop is, and a formula comparing an item
CHANGED_FROM_C = {
    "a list changed from C": (HEAP, {"xs": [3, 5]}, (5, 4), compares_the_largest),
    "a dict changed from C": (STORED, {"d": {"a": 1}}, (4, 4), compares_a),
    "a list of lists changed from C": (
        HEAP_OF_LISTS,
        {"xs": [[3], [5]]},
        (5, 4),
        compares_the_largest_first,
    ),
    "a dict of a list of dicts changed from C": (
        STORED_LISTS,
        {"d": {"a": [{"b": 1}]}},
        (4, 4),
        compares_a_s_first_b,
    ),
}

type _Judged = list[Branch | Fact | Downgrade]


def written_and_in_use(
    source: str,
    going_in: Mapping[str, object],
    loop: tuple[int, int],
    formula: Callable[[Mapping[str, object]], Mapping[str, object]],
) -> tuple[_Judged, _Judged, int]:
    """The forks, facts and downgrades of a call with the loop followed as written and of one
    with the loop in use, and how many times the formula ran."""
    calls: list[Mapping[str, object]] = []

    def counting(values: Mapping[str, object]) -> Mapping[str, object]:
        calls.append(values)
        return formula(values)

    seen: list[_Judged] = []
    for loops in ({}, {loop: LoopInUse(("s", "t", *going_in), ("t",), counting)}):
        f = hooked(source)
        with using(loops) as sink:
            (value,) = bind(going_in, sink).values()
            f(value, "ab")
        seen.append([each for each in sink if isinstance(each, Branch | Fact | Downgrade)])
    written, in_use = seen
    return written, in_use, len(calls)


@pytest.mark.parametrize(
    ("source", "going_in", "loop"),
    [row[:3] for row in CHANGED_FROM_C.values()],
    ids=list(CHANGED_FROM_C),
)
def test_the_copy_of_a_list_or_dict_changed_from_c_leaves_the_target_s_own_alone(
    source: str, going_in: Mapping[str, object], loop: tuple[int, int]
) -> None:
    written, in_use, calls = written_and_in_use(source, going_in, loop, lengthened)

    assert calls == 1
    assert in_use == written
    assert any(type(each) is Downgrade for each in written)
    assert not any(each.site.file.endswith("copy.py") for each in in_use)


@pytest.mark.parametrize(
    ("source", "going_in", "loop", "formula"),
    list(CHANGED_FROM_C.values()),
    ids=list(CHANGED_FROM_C),
)
def test_a_formula_comparing_an_item_of_such_a_copy_records_what_the_loop_records(
    source: str,
    going_in: Mapping[str, object],
    loop: tuple[int, int],
    formula: Callable[[Mapping[str, object]], Mapping[str, object]],
) -> None:
    written, in_use, calls = written_and_in_use(source, going_in, loop, formula)

    assert calls == 1
    assert in_use == written


HOLDS_ITSELF = """\
def f(xs, s):
    list.append(xs, xs)
    t = 0
    for c in s:
        t += 1
        len(xs)
    return t
"""


def test_the_copy_of_a_list_c_made_hold_itself_is_plain_and_holds_itself() -> None:
    seen: list[object] = []

    def keeping(values: Mapping[str, object]) -> Mapping[str, object]:
        seen.append(values["xs"])
        return lengthened(values)

    written, in_use, calls = written_and_in_use(HOLDS_ITSELF, {"xs": [[3]]}, (4, 4), keeping)

    (xs,) = seen
    assert (calls, in_use) == (1, written)
    assert type(xs) is list
    inner, itself = cast(list[Any], xs)
    assert (type(inner), type(inner[0])) == (list, int)
    assert itself is xs
