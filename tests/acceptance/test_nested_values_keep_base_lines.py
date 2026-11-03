"""Lines base covers stay covered once a float or a bool inside an argument is tracked: under
tracked keys and joins, and across a dict's walk. Each entry of ``NAMED_LOSSES`` is a tracked
value meeting an operation with no form, a `%` operand among them (plan nested-floats-bools,
5.10): a downgrade names the operation's line, and the lines the entry lists stay missed."""

import json

import pytest

from tests.acceptance.test_nested_floats_and_bools import (
    ACCEPTED,
    ITEMS,
    MIXED,
    NESTED,
    QUICK,
    SEARCHES,
    VALUES,
    lines_of,
    missing_lines,
    return_line,
)

# the walks of many rows
ROW_WALKS = "targets.nested.row_walks"

# the formats and the reads whose results turn plain
PLAIN = "targets.nested.turned_plain"

# many rows, which a walk once read in time that grew with each row
MANY_ROWS = {"g": [[1]] * 16_000, "n": 1}


@pytest.mark.parametrize(
    ("function", "seed"),
    [
        ("two_keys", {"d": {"x": {"p": 1, "q": 5}}, "a": "x", "b": "p"}),
        ("row_and_key", {"rows": [{"a": 1, "b": 5}], "i": 0, "k": "a"}),
        ("last_row_key", {"rows": [{"a": 1, "b": 2}], "k": "a"}),
        ("joined_int_row", {"ys": [[1]], "grid": [[2], [0.5]]}),
        ("joined_int_row", {"ys": [[1]], "grid": [[2], 0.5]}),
        ("joined_int_row", {"ys": [[1]], "grid": [[2], True]}),
        ("joined_int_row", {"ys": [[1]], "grid": [[2], 0.5, 1]}),
        ("appended_then_read", {"xs": [1], "i": 1, "f": 0.5}),
        ("flag_value_in_a_sum", {"ys": [0, 1, 2], "data": {"flag": False}}),
        ("rounds_in_a_walk", {"d": {"a": 1}, "xs": [0.5]}),
        ("formats_in_a_walk", {"d": {"a": 1}, "xs": [0.5]}),
        ("percent_in_a_walk", {"d": {"a": 1}, "xs": [0.5]}),
        ("powers_in_a_walk", {"d": {"a": 1}, "xs": [0.5]}),
    ],
)
def test_a_line_base_covers_stays_covered(function: str, seed: object) -> None:
    target = f"{NESTED}::{function}"
    lines = lines_of(target, seed, *QUICK)
    assert missing_lines(target, lines) == set()


@pytest.mark.parametrize(
    "function",
    [
        "walk_of_reversed_rows",
        "walk_of_growing_rows",
        "walk_of_rows_given_floats",
        "walk_of_rows_given_rows",
    ],
)
def test_a_walk_of_many_rows_covers_every_line_in_its_budget(function: str) -> None:
    target = f"{ROW_WALKS}::{function}"
    lines = lines_of(target, MANY_ROWS, "--budget", "15", "--solver-timeout", "3")
    assert missing_lines(target, lines) == set()


@pytest.mark.parametrize(
    ("function", "seed"),
    [
        ("cut_row_in_a_walk", {"d": {"a": 1}, "g": [[0.5], [0.5]], "i": 1}),
        ("picked_dict_in_a_walk", {"d": {"a": 1}, "rows": [{"x": 0.5}, {"x": 0.5}], "i": 1}),
    ],
)
def test_a_float_left_plain_in_a_walk_lets_the_walk_choose_a_key(
    function: str, seed: object
) -> None:
    target = f"{NESTED}::{function}"
    lines = lines_of(target, seed, *QUICK)
    assert return_line(target, "hit") not in missing_lines(target, lines)


# each run that loses a line to an operation with no form: the target, the seed, the downgrade
# that names it, the line the operation is on, and the lines it loses
NAMED_LOSSES = [
    (f"{NESTED}::flag_indexes", {"ys": [0, 1], "flags": [False]}, "__getitem__", 313, [314]),
    (f"{NESTED}::flag_pops", {"ys": [0, 1], "flags": [False]}, "pop", 319, [321]),
    (f"{NESTED}::flag_cuts_a_list", {"ys": [0, 1], "flags": [False]}, "__getitem__", 326, [327]),
    (f"{NESTED}::flag_stores", {"ys": [0, 1], "flags": [False]}, "__setitem__", 332, [334]),
    (f"{NESTED}::flag_repeats_a_list", {"ys": [0, 1], "flags": [True]}, "__mul__", 339, [340]),
    (f"{NESTED}::flag_cuts_a_str", {"s": "abc", "flags": [True]}, "__getitem__", 345, [347]),
    (f"{NESTED}::flag_repeats_a_str", {"s": "ab", "flags": [True]}, "__mul__", 351, [352]),
    (f"{NESTED}::flag_picks_a_char", {"s": "abc", "flags": [True]}, "__getitem__", 357, [358]),
    (f"{NESTED}::float_as_int_pads", {"s": "a", "xs": [3.5]}, "ljust", 363, [364]),
    (
        f"{NESTED}::flag_value_indexes",
        {"ys": [0, 1], "data": {"flag": False}},
        "__getitem__",
        375,
        [376],
    ),
    (f"{NESTED}::flag_as_a_key", {"d": {"0": 1}, "flags": [False]}, "__getitem__", 381, [382]),
    (
        f"{NESTED}::flag_searches_keys",
        {"d": {"0": 1}, "flags": [False]},
        "__contains__",
        387,
        [388],
    ),
    (
        f"{NESTED}::cut_row_in_a_walk",
        {"d": {"a": 1}, "g": [[0.5], [0.5]], "i": 1},
        "__getitem__",
        426,
        [427],
    ),
    (
        f"{NESTED}::picked_dict_in_a_walk",
        {"d": {"a": 1}, "rows": [{"x": 0.5}, {"x": 0.5}], "i": 1},
        "__getitem__",
        435,
        [436],
    ),
    (
        f"{NESTED}::flag_in_a_walk",
        {"d": {"a": 1}, "ys": [0, 1], "flags": [False]},
        "__getitem__",
        444,
        [446],
    ),
    (f"{NESTED}::percent_beside_a_name", {"name": "al", "scores": [0.5]}, "__mod__", 457, [458]),
    (f"{NESTED}::name_beside_a_float", {"s": "a", "xs": [0.5]}, "__mod__", 483, [484]),
    (f"{PLAIN}::hex_beside_a_number", {"x": 1, "y": 0}, "__mod__", 2, [5]),
    (f"{PLAIN}::precision_beside_a_name", {"xs": [0.5], "name": "a"}, "__mod__", 11, [14]),
    (f"{PLAIN}::text_as_a_key", {"d": {"1.5": 1}, "xs": [1.5]}, "__str__", 22, [23]),
    (f"{PLAIN}::percent_as_a_key", {"d": {"1.5": 1}, "xs": [1.5]}, "__mod__", 30, [31]),
    (f"{PLAIN}::repr_beside_a_number", {"s": "\U000e0001", "y": 0}, "__mod__", 66, [68]),
    (f"{PLAIN}::ascii_beside_a_number", {"s": "\U00030000", "y": 0}, "__mod__", 73, [75]),
    (f"{PLAIN}::list_beside_a_number", {"xs": [1], "y": 0}, "__mod__", 80, [82]),
    (f"{PLAIN}::dict_beside_a_number", {"d": {"k": 1}, "y": 0}, "__mod__", 87, [89]),
    (f"{PLAIN}::hex_that_ends", {"x": 1, "y": 0}, "__mod__", 109, [111]),
    (f"{PLAIN}::float_that_ends", {"x": 0.5, "y": 0}, "__mod__", 116, [118]),
    (f"{PLAIN}::item_that_ends", {"xs": [0.5], "y": 0}, "__mod__", 123, [125]),
]


@pytest.mark.parametrize(("target", "seed", "name", "at", "lost"), NAMED_LOSSES)
def test_a_line_lost_to_an_operation_with_no_form_is_named_where_it_is_lost(
    target: str, seed: object, name: str, at: int, lost: list[int]
) -> None:
    lines = lines_of(target, seed, *QUICK)
    named = {(entry["name"], entry["line"]) for line in lines for entry in _downgrades(line)}
    assert (name, at) in named, named
    assert set(lost) <= missing_lines(target, lines)


def _downgrades(line: dict[str, object]) -> list[dict[str, object]]:
    """The downgrades a printed line lists."""
    entries = line["downgrades"]
    assert isinstance(entries, list), line
    return entries


def test_a_line_only_legacy_covers_in_this_story_is_a_named_loss() -> None:
    modules = (NESTED, ROW_WALKS, PLAIN, MIXED, SEARCHES, VALUES, ITEMS)
    records = [json.loads(line) for line in ACCEPTED.read_text().splitlines()]
    ours = [r for r in records if str(r.get("target")).startswith(modules)]
    named = [(target, seed, lost) for target, seed, *_, lost in NAMED_LOSSES]
    assert ours
    lost = [r for r in ours if r["only_legacy"]]
    assert all((r["target"], r["seed"], r["only_legacy"]) in named for r in lost), lost


@pytest.mark.parametrize("function", ["key_as_a_float_in_a_format", "key_as_a_tolerance"])
def test_a_float_made_from_a_walk_key_keeps_every_answer_on_its_plan(function: str) -> None:
    lines = lines_of(f"{NESTED}::{function}", {"d": {"1": 1}}, "--budget", "10")
    assert [line["mismatch_at"] for line in lines if line["mismatch_at"] is not None] == []
