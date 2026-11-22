"""A loop in use keeps, as it starts, a copy of each list or dict going in, of the list or dict
itself: its formula, and the record of a run it fails on, read the list or dict as it went in
after the loop removes its items. A tracked one reaches the formula as a tracked copy one level
deep, or, when its length changed from C, as a plain copy in which each list, tuple and dict that
holds a tracked value, at any depth, is a plain copy too, and each tracked int, float, str or bool,
a dict's keys included, is its plain value. The plain one records what the loop as written
records."""

import sys
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


HEAP_OF_HELD = """\
import heapq
def f(xs, p, s):
    heapq.heappush(xs, {held})
    t = 0
    for c in s:
        t += 1
        len(xs)
    return t
"""
STORED_KEY = """\
def f(d, k, s):
    dict.__setitem__(d, k, 9)
    t = 0
    for c in s:
        t += 1
        len(d)
    return t
"""


def compares_the_ints_the_first_holds(values: Mapping[str, object]) -> Mapping[str, object]:
    """HEAP_OF_HELD's formula, comparing each int the list's first item holds at any depth, a
    dict's keys and values included."""
    inside = [cast(list[Any], values["xs"])[0]]
    while inside:
        each = inside.pop()
        if isinstance(each, dict):
            inside.extend([*each, *each.values()])
        elif isinstance(each, list | tuple):
            inside.extend(each)
        elif isinstance(each, int):
            assert each > 4
    return lengthened(values)


def compares_the_keys(values: Mapping[str, object]) -> Mapping[str, object]:
    """STORED_KEY's formula, comparing each key of the dict going in."""
    d = values["d"]
    assert isinstance(d, dict)
    assert all(key != "z" for key in cast(dict[str, int], d))
    return lengthened(values)


# a list or dict going in that C code changed, with the values the call takes before the str,
# where its loop is, and a formula comparing what it holds
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
    "a list of Python's own lists changed from C": (
        HEAP_OF_HELD.format(held="[p]"),
        {"xs": [], "p": 7},
        (5, 4),
        compares_the_ints_the_first_holds,
    ),
    "a list of tuples changed from C": (
        HEAP_OF_HELD.format(held="(p, 'task')"),
        {"xs": [], "p": 7},
        (5, 4),
        compares_the_ints_the_first_holds,
    ),
    "a list of tuples of a tuple and a list changed from C": (
        HEAP_OF_HELD.format(held="((p,), [p])"),
        {"xs": [], "p": 7},
        (5, 4),
        compares_the_ints_the_first_holds,
    ),
    "a list of Python's own dicts changed from C": (
        HEAP_OF_HELD.format(held="{p: p}"),
        {"xs": [], "p": 7},
        (5, 4),
        compares_the_ints_the_first_holds,
    ),
    "a dict given a tracked key from C": (
        STORED_KEY,
        {"d": {"a": 1}, "k": "x"},
        (4, 4),
        compares_the_keys,
    ),
}

type _Judged = list[Branch | Fact | Downgrade]


def written_and_in_use(
    source: str,
    going_in: Mapping[str, object],
    loop: tuple[int, int],
    formula: Callable[[Mapping[str, object]], Mapping[str, object]],
) -> tuple[_Judged, _Judged, int]:
    """The forks, facts and downgrades of a call on the values going in, bound, and a str, with
    the loop followed as written and with the loop in use, and how many times the formula ran."""
    calls: list[Mapping[str, object]] = []

    def counting(values: Mapping[str, object]) -> Mapping[str, object]:
        calls.append(values)
        return formula(values)

    seen: list[_Judged] = []
    for loops in ({}, {loop: LoopInUse(("s", "t", *going_in), ("t",), counting)}):
        f = hooked(source)
        with using(loops) as sink:
            f(*bind(going_in, sink).values(), "ab")
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
def test_a_formula_comparing_what_such_a_copy_holds_records_what_the_loop_records(
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


HOLDS_A_TUPLE_OF_ITSELF = """\
def f(xs, p, s):
    list.append(xs, (xs, p))
    t = 0
    for c in s:
        t += 1
        len(xs)
    return t
"""


def test_the_copy_of_a_list_c_made_hold_a_tuple_of_itself_holds_a_tuple_of_its_copy() -> None:
    seen: list[object] = []

    def keeping(values: Mapping[str, object]) -> Mapping[str, object]:
        seen.append(values["xs"])
        return lengthened(values)

    going_in = {"xs": [3], "p": 7}
    written, in_use, calls = written_and_in_use(HOLDS_A_TUPLE_OF_ITSELF, going_in, (4, 4), keeping)

    (xs,) = seen
    assert (calls, in_use) == (1, written)
    first, (itself, p) = cast(list[Any], xs)
    assert (type(xs), type(first), type(p)) == (list, int, int)
    assert itself is xs


HOLDS_PLAIN = """\
import heapq
def f(xs, held, s):
    heapq.heappush(xs, held)
    t = 0
    for c in s:
        t += 1
        len(xs)
    return t
"""


@pytest.mark.parametrize("held", [(0, "task"), [0, ["task"]], {"k": (0,)}], ids=type)
def test_the_copy_keeps_a_container_that_holds_nothing_tracked_as_it_is(held: object) -> None:
    seen: list[object] = []

    def keeping(values: Mapping[str, object]) -> Mapping[str, object]:
        seen.append(values["xs"])
        return lengthened(values)

    f = hooked(HOLDS_PLAIN)
    with using({(5, 4): LoopInUse(("s", "t", "xs"), ("t",), keeping)}) as sink:
        f(bind({"xs": []}, sink)["xs"], held, "ab")

    (xs,) = seen
    assert type(xs) is list
    assert cast(list[object], xs)[0] is held
    assert drops(sink) == []


NESTED_DEEP = """\
def f(xs, s):
    list.append(xs, 9)
    t = 0
    for c in s:
        t += 1
        len(xs)
    return t
"""


def compares_the_deepest(values: Mapping[str, object]) -> Mapping[str, object]:
    """NESTED_DEEP's formula, comparing the int at the bottom of the lists going in."""
    each = cast(list[Any], values["xs"])[0]
    while isinstance(each, list):
        each = each[0]
    assert each > 0
    return lengthened(values)


def test_the_plain_copy_of_lists_nested_past_the_recursion_limit_reaches_the_formula() -> None:
    nested: list[Any] = [1]
    for _ in range(sys.getrecursionlimit() * 2):
        nested = [nested]

    written, in_use, calls = written_and_in_use(
        NESTED_DEEP, {"xs": nested}, (4, 4), compares_the_deepest
    )

    assert calls == 1
    assert in_use == written
