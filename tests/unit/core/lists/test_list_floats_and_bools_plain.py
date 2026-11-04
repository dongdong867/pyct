"""A float or a bool of a tracked list: a list that turns plain turns its floats plain too, a
read twice is one object, and a use no term follows is plain and named by a downgrade."""

import math
from typing import Any

import pytest

from pyct.binding.bind import bind
from pyct.core.foundation.branch import SinkItem
from pyct.core.lists.list_compares import matches
from pyct.core.lists.list_state import plain
from tests.unit.core.lists.test_list_floats_and_bools import bound, downgrades, forks


def test_a_list_that_turns_plain_turns_its_floats_and_bools_plain_with_it() -> None:
    xs, sink = bound([0.5, True])

    xs.turn_plain()

    assert [type(item) for item in list.copy(xs)] == [float, bool]
    assert type(xs[0]) is float
    assert forks(sink) == []


def test_an_answer_of_a_list_changed_without_its_methods_is_plain_and_named() -> None:
    xs, sink = bound([0.5])

    list.__setitem__(xs, 0, 2.5)

    assert type(xs[0]) is float
    assert downgrades(sink) == ["__getitem__"]


def test_a_float_read_twice_is_one_object_to_a_list() -> None:
    xs, sink = bound([math.nan])

    assert matches(xs[0], xs[0])
    assert ["==", ["[float]", "xs", 0], ["[float]", "xs", 0]] not in forks(sink)


def test_two_floats_computed_alike_are_not_one_object() -> None:
    xs, sink = bound([math.nan])

    assert not matches(xs[0] + 0.0, xs[0] + 0.0)
    assert any(isinstance(item, list) and item[0] == "==" for item in forks(sink))


def test_a_list_searched_for_its_own_nan_finds_it_as_python_does() -> None:
    xs, _ = bound([math.nan])
    plainly = [math.nan]

    assert (xs[0] in xs) is (plainly[0] in plainly)
    assert (xs == xs) is (plainly == plainly)


def test_a_compare_of_two_positions_still_forks() -> None:
    xs, sink = bound([0.5, 0.5])

    assert matches(xs[0], xs[1])
    assert ["==", ["[float]", "xs", 0], ["[float]", "xs", 1]] in forks(sink)


def test_a_read_past_the_end_raises_after_its_fork() -> None:
    xs, sink = bound([0.5])
    plainly = [0.5]
    with pytest.raises(IndexError) as raised:
        plainly[3]
    with pytest.raises(IndexError) as ours:
        xs[3]

    assert str(ours.value) == str(raised.value)
    assert forks(sink)[-1] == [">", ["len", "xs"], 3]


def test_a_tracked_bool_as_an_index_is_a_downgrade() -> None:
    sink: list[SinkItem] = []
    args: Any = bind({"xs": [5, 6], "flags": [True]}, sink)

    assert plain(args["xs"][args["flags"][0]]) == 6
    assert "__getitem__" in downgrades(sink)


@pytest.mark.parametrize("seed", [[True], [1.5]])
def test_a_tracked_bool_or_float_as_a_key_is_a_downgrade(seed: list[object]) -> None:
    sink: list[SinkItem] = []
    args: Any = bind({"table": {1: "a", 1.5: "b", "k": "c"}, "xs": seed}, sink)
    table: dict[Any, str] = {1: "a", 1.5: "b"}

    assert args["table"].get(args["xs"][0]) == table[plain(args["xs"][0])]
    assert downgrades(sink)


def test_a_list_built_on_a_row_a_cut_picks_hands_its_float_out_plain_and_named() -> None:
    sink: list[SinkItem] = []
    args: Any = bind({"ys": [1], "g": [[0.5], [0.5]], "i": 1}, sink)

    item = (args["ys"] + args["g"][args["i"] :][0])[1]

    assert type(item) is float
    assert downgrades(sink)


@pytest.mark.parametrize(
    "takes",
    [lambda ys, row: ys.extend(row), lambda ys, row: ys.__setitem__(slice(1, 1), row)],
    ids=["extend", "a slice set"],
)
def test_a_list_that_takes_in_a_row_a_cut_picks_hands_its_float_out_plain_and_named(
    takes: Any,
) -> None:
    sink: list[SinkItem] = []
    args: Any = bind({"ys": [1], "g": [[0.5], [0.5]], "i": 1}, sink)
    ys = args["ys"]

    takes(ys, args["g"][args["i"] :][0])

    assert type(ys[1]) is float
    assert downgrades(sink)
