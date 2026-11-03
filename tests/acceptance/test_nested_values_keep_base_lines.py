"""Every line base covers stays covered once a float or a bool inside an argument is tracked:
under tracked keys and joins, beside a str a format writes, and across a dict's walk. Where such a
number meets an operation with no form, the run names the line it loses."""

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
        ("percent_beside_a_name", {"name": "al", "scores": [0.5]}),
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
    target = f"{NESTED}::{function}"
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


# each run that loses a line to an operation with no form: the downgrade that names it, the line
# the operation is on, and the lines it loses
NAMED_LOSSES = [
    ("flag_indexes", {"ys": [0, 1], "flags": [False]}, "__getitem__", 313, [314]),
    ("flag_pops", {"ys": [0, 1], "flags": [False]}, "pop", 319, [321]),
    ("flag_cuts_a_list", {"ys": [0, 1], "flags": [False]}, "__getitem__", 326, [327]),
    ("flag_stores", {"ys": [0, 1], "flags": [False]}, "__setitem__", 332, [334]),
    ("flag_repeats_a_list", {"ys": [0, 1], "flags": [True]}, "__mul__", 339, [340]),
    ("flag_cuts_a_str", {"s": "abc", "flags": [True]}, "__getitem__", 345, [347]),
    ("flag_repeats_a_str", {"s": "ab", "flags": [True]}, "__mul__", 351, [352]),
    ("flag_picks_a_char", {"s": "abc", "flags": [True]}, "__getitem__", 357, [358]),
    ("float_as_int_pads", {"s": "a", "xs": [3.5]}, "ljust", 363, [364]),
    ("flag_value_indexes", {"ys": [0, 1], "data": {"flag": False}}, "__getitem__", 375, [376]),
    ("flag_as_a_key", {"d": {"0": 1}, "flags": [False]}, "__getitem__", 381, [382]),
    ("flag_searches_keys", {"d": {"0": 1}, "flags": [False]}, "__contains__", 387, [388]),
    ("cut_row_in_a_walk", {"d": {"a": 1}, "g": [[0.5], [0.5]], "i": 1}, "__getitem__", 426, [427]),
    (
        "picked_dict_in_a_walk",
        {"d": {"a": 1}, "rows": [{"x": 0.5}, {"x": 0.5}], "i": 1},
        "__getitem__",
        435,
        [436],
    ),
    (
        "flag_in_a_walk",
        {"d": {"a": 1}, "ys": [0, 1], "flags": [False]},
        "__getitem__",
        444,
        [446],
    ),
]


@pytest.mark.parametrize(("function", "seed", "name", "at", "lost"), NAMED_LOSSES)
def test_a_line_lost_to_an_operation_with_no_form_is_named_where_it_is_lost(
    function: str, seed: object, name: str, at: int, lost: list[int]
) -> None:
    target = f"{NESTED}::{function}"
    lines = lines_of(target, seed, *QUICK)
    named = {(entry["name"], entry["line"]) for line in lines for entry in _downgrades(line)}
    assert (name, at) in named, named


def _downgrades(line: dict[str, object]) -> list[dict[str, object]]:
    """The downgrades a printed line lists."""
    entries = line["downgrades"]
    assert isinstance(entries, list), line
    return entries


def test_a_line_only_legacy_covers_in_this_story_is_a_named_loss() -> None:
    modules = (NESTED, MIXED, SEARCHES, VALUES, ITEMS)
    records = [json.loads(line) for line in ACCEPTED.read_text().splitlines()]
    ours = [r for r in records if str(r.get("target")).startswith(modules)]
    named = [(f"{NESTED}::{function}", seed, lost) for function, seed, *_, lost in NAMED_LOSSES]
    assert ours
    lost = [r for r in ours if r["only_legacy"]]
    assert all((r["target"], r["seed"], r["only_legacy"]) in named for r in lost), lost


@pytest.mark.parametrize("function", ["key_as_a_float_in_a_format", "key_as_a_tolerance"])
def test_a_float_made_from_a_walk_key_keeps_every_answer_on_its_plan(function: str) -> None:
    lines = lines_of(f"{NESTED}::{function}", {"d": {"1": 1}}, "--budget", "10")
    assert [line["mismatch_at"] for line in lines if line["mismatch_at"] is not None] == []
