"""A float or a bool read from a tracked list: tracked where the solver can type it, else plain
and named by a downgrade, and a list that turns plain turns its floats plain too."""

import math
from typing import Any

import pytest

from pyct.binding.bind import bind
from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, Downgrade, Expression, SinkItem
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt
from pyct.core.list_compares import matches
from pyct.core.list_forms import written
from pyct.core.list_state import kind_of, plain


def bound(value: list[Any], name: str = "xs") -> tuple[Any, list[SinkItem]]:
    """A list as a run binds it, and its sink."""
    sink: list[SinkItem] = []
    return bind({name: value}, sink)[name], sink


# the ways a list takes in a value, each with the position the value lands on
TAKING_IN = [
    (lambda xs, value: xs.append(value), 2),
    (lambda xs, value: xs.extend([value]), 2),
    (lambda xs, value: xs.insert(1, value), 1),
    (lambda xs, value: xs.__setitem__(1, value), 1),
]


def forks(sink: list[SinkItem]) -> list[Expression]:
    return [item.expression for item in sink if isinstance(item, Branch)]


def downgrades(sink: list[SinkItem]) -> list[str]:
    return [item.name for item in sink if isinstance(item, Downgrade)]


def test_a_tracked_float_has_its_kind_and_plain_value() -> None:
    value = ConcolicFloat.made(2.5, "x", [])

    assert kind_of(value) == "float"
    assert type(plain(value)) is float
    assert plain(value) == 2.5


def test_a_change_writes_a_tracked_float_as_its_expression() -> None:
    assert written(ConcolicFloat.made(2.5, "x", []), "append") == "x"


@pytest.mark.parametrize(
    ("value", "kind"),
    [(0.5, ConcolicFloat), (True, ConcolicBool)],
)
def test_an_argument_s_float_or_bool_at_a_position_comes_out_as_indexed(
    value: object, kind: type
) -> None:
    xs, _ = bound([1, "a", value])

    item = xs[2]
    assert type(item) is kind
    assert item.expression == ["[]", "xs", 2]


def test_an_item_from_the_end_of_a_list_that_holds_a_float_comes_out_as_indexed() -> None:
    xs, _ = bound([1, 0.5])

    assert xs[-1].expression == ["[]", "xs", -1]
    assert xs[-2].expression == ["[]", "xs", -2]
    assert type(xs[-2]) is ConcolicInt


def test_a_list_inside_at_places_the_target_wrote_is_read_as_an_argument_s() -> None:
    sink: list[SinkItem] = []
    d: Any = bind({"d": {"a": [1, 0.5]}}, sink)["d"]

    assert d["a"][1].expression == ["[]", ["[]", "d", "'a'"], 1]


def test_a_float_under_a_tracked_index_comes_out_as_indexed_where_every_item_is_a_float() -> None:
    sink: list[SinkItem] = []
    args: Any = bind({"xs": [0.5, 1.5], "i": 1}, sink)

    item = args["xs"][args["i"]]
    assert type(item) is ConcolicFloat
    assert item.expression == ["[]", "xs", "i"]


def test_a_tracked_index_into_a_mixed_list_is_a_downgrade() -> None:
    sink: list[SinkItem] = []
    args: Any = bind({"xs": [1, 0.5], "i": 1}, sink)

    assert plain(args["xs"][args["i"]]) == 0.5
    assert downgrades(sink) == ["__getitem__"]


def test_an_item_of_a_list_of_one_kind_built_from_an_argument_comes_out_as_indexed() -> None:
    xs, _ = bound([0.5])

    ys = xs + [2.5]

    assert ys[1].expression == ["[]", ["+", "xs", ["[,]", 2.5]], 1]
    assert ys[0].expression == ["[]", ["+", "xs", ["[,]", 2.5]], 0]


def test_a_none_beside_floats_leaves_a_built_list_one_kind() -> None:
    xs, _ = bound([0.5, None])

    ys = xs + [2.5]

    assert ys[2].expression == ["[]", ["+", "xs", ["[,]", 2.5]], 2]


def test_a_float_the_target_added_to_ints_comes_out_plain_with_no_downgrade() -> None:
    xs, sink = bound([1])

    item = (xs + [2.5])[1]

    assert type(item) is float
    assert downgrades(sink) == []


def test_an_argument_s_float_in_a_list_built_with_other_kinds_is_plain_and_named() -> None:
    xs, sink = bound([1, 0.5])

    item = (xs + ["a"])[1]

    assert type(item) is float
    assert downgrades(sink) == ["__getitem__"]


def test_an_int_in_a_list_of_other_kinds_comes_out_as_indexed_as_it_did() -> None:
    xs, _ = bound([1, 0.5])

    form = ["+", "xs", ["[,]", "'a'"]]

    assert (xs + ["a"])[0].expression == ["[]", form, 0]


@pytest.mark.parametrize(
    ("grid", "kind"), [([[0.5], [1.5]], ConcolicFloat), ([[False], [True, None]], ConcolicBool)]
)
@pytest.mark.parametrize("index", [0, -1])
def test_a_row_an_index_picks_from_rows_of_one_kind_hands_its_item_out_as_indexed(
    grid: list[list[object]], kind: type, index: int
) -> None:
    sink: list[SinkItem] = []
    args: Any = bind({"grid": grid, "i": index}, sink)

    item = (args["grid"][args["i"]] if index == 0 else args["grid"][index])[0]

    assert type(item) is kind
    assert item.expression == ["[]", ["[]", "grid", "i" if index == 0 else -1], 0]
    assert downgrades(sink) == []


@pytest.mark.parametrize("index", [1, -1])
def test_a_float_in_a_row_an_index_picks_from_rows_of_other_kinds_is_plain_and_named(
    index: int,
) -> None:
    sink: list[SinkItem] = []
    args: Any = bind({"grid": [[1], [0.5]], "i": index}, sink)

    item = args["grid"][args["i"]][0]

    assert type(item) is float
    assert downgrades(sink) == ["__getitem__"]


@pytest.mark.parametrize(
    ("seed", "read"),
    [
        ({"xs": [1, 0.5], "i": 1}, lambda a: a["xs"][a["i"] :][0]),
        ({"xs": [1, 0.5], "i": 1}, lambda a: a["xs"][-1:][0]),
        ({"xs": [1, 0.5], "i": 1}, lambda a: a["xs"][1:][0]),
        ({"xs": [0.5, 1], "ys": [1]}, lambda a: (a["ys"] + a["xs"])[1]),
        ({"xs": [0.5, 1], "ys": [1]}, lambda a: (a["xs"] + a["ys"])[0]),
        ({"xs": [0.5, 1], "i": 0}, lambda a: (a["xs"] * 2)[2]),
    ],
)
def test_a_float_in_a_built_list_of_other_kinds_is_plain_and_named(
    seed: dict[str, object], read: Any
) -> None:
    sink: list[SinkItem] = []
    args: Any = bind(seed, sink)

    assert type(read(args)) is float
    assert downgrades(sink) == ["__getitem__"]


@pytest.mark.parametrize(
    ("change", "position"),
    [
        (lambda xs, i: xs.append(0.5), 1),
        (lambda xs, i: xs.extend([2]), 1),
        (lambda xs, i: xs.insert(0, 2), 2),
        (lambda xs, i: xs.insert(i, 2), 2),
        (lambda xs, i: xs.reverse(), 0),
        (lambda xs, i: xs.__setitem__(0, 2), 1),
        (lambda xs, i: xs.__delitem__(0), 0),
        (lambda xs, i: xs.pop(-2), 0),
    ],
)
def test_a_float_read_after_a_change_to_a_list_of_other_kinds_is_plain_and_named(
    change: Any, position: int
) -> None:
    sink: list[SinkItem] = []
    args: Any = bind({"xs": [1, 0.5], "i": 0}, sink)
    xs = args["xs"]
    change(xs, args["i"])
    before = len(downgrades(sink))

    assert type(xs[position]) is float
    assert downgrades(sink)[before:] == ["__getitem__"]


@pytest.mark.parametrize(("change", "position"), TAKING_IN)
def test_an_argument_s_float_a_list_of_ints_takes_in_is_plain_and_named(
    change: Any, position: int
) -> None:
    sink: list[SinkItem] = []
    args: Any = bind({"xs": [1, 2], "fs": [0.5]}, sink)
    xs = args["xs"]
    change(xs, args["fs"][0])

    assert type(xs[position]) is float
    assert downgrades(sink) == ["__getitem__"]


@pytest.mark.parametrize(("change", "position"), TAKING_IN)
def test_a_float_parameter_a_list_of_ints_takes_in_comes_out_as_stored(
    change: Any, position: int
) -> None:
    sink: list[SinkItem] = []
    args: Any = bind({"xs": [1, 2], "f": 0.5}, sink)
    xs = args["xs"]
    change(xs, args["f"])

    item = xs[position]
    assert type(item) is ConcolicFloat
    assert item.expression == "f"
    assert downgrades(sink) == []


@pytest.mark.parametrize(
    ("grid", "built"),
    [
        ([[1], [False]], lambda grid, i: grid[-1][0:]),
        ([[0.5], [1]], lambda grid, i: grid[i] + [1.5]),
        ([[False], [1]], lambda grid, i: grid[i] + [True]),
        ([[1], [False]], lambda grid, i: next(reversed(grid))[0:]),
        ([[0.5], [0.5]], lambda grid, i: grid[i:][0]),
    ],
)
def test_a_row_the_solver_cannot_place_hands_out_its_float_or_bool_plain(
    grid: list[list[object]], built: Any
) -> None:
    sink: list[SinkItem] = []
    args: Any = bind({"grid": grid, "i": 0}, sink)

    item = built(args["grid"], args["i"])[0]

    assert type(item) in (float, bool)
    assert downgrades(sink)


@pytest.mark.parametrize(
    ("seed", "read"),
    [
        ({"g": [[0.5], [0.5]], "i": 1}, lambda a: a["g"][a["i"] :][0][0]),
        ({"ys": [[1]], "g": [[0.5], [1]]}, lambda a: (a["ys"] + a["g"])[1][0]),
        ({"d": {"a": [0.5], "b": [0.5]}, "k": "b"}, lambda a: a["d"][a["k"]][0]),
        ({"rows": [{"x": 0.5}, {"x": 0.5}], "i": 1}, lambda a: a["rows"][a["i"]]["x"]),
        ({"rows": [{"x": 0.5}, {"x": 0.5}]}, lambda a: a["rows"][-1]["x"]),
        ({"rows": [{"x": True}, {"x": True}]}, lambda a: a["rows"][-1]["x"]),
        ({"rows": [{"x": [0.5]}, {"x": [0.5]}]}, lambda a: a["rows"][-1]["x"][0]),
        ({"rows": [{"x": 0.5}], "k": "x"}, lambda a: a["rows"][-1][a["k"]]),
    ],
)
def test_a_float_under_a_row_or_dict_a_cut_or_index_picks_is_plain_and_named(
    seed: dict[str, object], read: Any
) -> None:
    sink: list[SinkItem] = []
    args: Any = bind(seed, sink)

    assert type(read(args)) in (float, bool)
    assert downgrades(sink)


@pytest.mark.parametrize(
    ("seed", "read", "expression"),
    [
        ({"d": {"a": 0.5}}, lambda a: a["d"]["a"], ["[]", "d", "'a'"]),
        ({"rows": [{"x": 0.5}]}, lambda a: a["rows"][0]["x"], ["[]", ["[]", "rows", 0], "'x'"]),
        ({"d": {"a": [1, 0.5]}}, lambda a: a["d"]["a"][1], ["[]", ["[]", "d", "'a'"], 1]),
        ({"g": [[1], [0.5]]}, lambda a: a["g"][1][0], ["[]", ["[]", "g", 1], 0]),
    ],
)
def test_a_float_at_places_the_target_wrote_stays_tracked(
    seed: dict[str, object], read: Any, expression: Expression
) -> None:
    sink: list[SinkItem] = []
    args: Any = bind(seed, sink)

    item = read(args)

    assert type(item) is ConcolicFloat
    assert item.expression == expression
    assert downgrades(sink) == []


def test_a_list_changed_thousands_of_times_reads_its_float() -> None:
    xs, _ = bound([0.5])
    for _ in range(5000):
        xs.append(0.5)

    assert type(xs[0]) is ConcolicFloat


def test_a_sorted_row_of_rows_of_one_kind_is_plain_like_any_list_built_on_a_picked_row() -> None:
    sink: list[SinkItem] = []
    args: Any = bind({"grid": [[2.5, 0.5], [1.5]], "i": 0}, sink)

    row = args["grid"][args["i"]]
    row.sort()

    assert type(row[0]) is float
    assert "__getitem__" in downgrades(sink)


def test_an_int_in_a_row_reached_by_a_tracked_index_comes_out_as_indexed_as_it_did() -> None:
    sink: list[SinkItem] = []
    args: Any = bind({"grid": [[1], [2]], "i": 0}, sink)

    assert args["grid"][args["i"]][0].expression == ["[]", ["[]", "grid", "i"], 0]


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
    assert ["==", ["[]", "xs", 0], ["[]", "xs", 0]] not in forks(sink)


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
    assert ["==", ["[]", "xs", 0], ["[]", "xs", 1]] in forks(sink)


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
