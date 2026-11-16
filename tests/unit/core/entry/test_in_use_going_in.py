"""A loop in use keeps, as it starts, a copy of each list or dict going in: its formula, and the
record of a run it fails on, read the values as they went in, whatever the loop does to them."""

from collections.abc import Mapping
from typing import Any, cast

from pyct.binding.bind import bind
from pyct.core.entry.in_use import LoopInUse
from pyct.core.foundation.branch import GoingIn, SinkItem
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
