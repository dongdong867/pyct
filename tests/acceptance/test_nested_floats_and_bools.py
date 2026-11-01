"""Acceptance tests for the follow-floats-and-bools-inside-dicts-and-lists child of the
run-with-nested-arguments story.

Each test spawns ``python -P -m pyct``: a float or a bool inside an argument is followed only if
its fork reaches the solver and the answer runs in the seed's shape.
"""

import ast
import json
import math
from pathlib import Path
from typing import Any

import pytest

from tests.acceptance.harness import (
    REPO_ROOT,
    forks_of,
    input_lines,
    run_pyct,
    summary_line,
    union_of,
)

NESTED = "targets.nested.floats_and_bools"
MIXED = "targets.lists.mixed_numbers"
SEARCHES = "targets.lists.float_searches"
VALUES = "targets.dicts.float_and_bool_values"
ITEMS = "targets.floats.items"
ACCEPTED = REPO_ROOT / "tools" / "compare_coverage" / "accepted-per-merge.jsonl"
QUICK = ("--budget", "4", "--solver-timeout", "2")
_ITEM_TESTS = ("3.0", "0.75", "2.5", "floor", "true")


def lines_of(target: str, seed: object, *argv: str) -> list[dict[str, object]]:
    """The input lines of a run, which must end with exit 0 and raise nothing it did not plan."""
    result = run_pyct(target, "--args", json.dumps(seed), *argv)
    assert result.returncode == 0, result.stderr
    return input_lines(result.stdout)


def solved(lines: list[dict[str, object]]) -> list[dict[str, object]]:
    """The lines of the inputs the solver handed back, without the seed's."""
    return [line for line in lines if line["source"] == "solver"]


def args_of(line: dict[str, object], name: str) -> Any:
    """One argument off a printed line."""
    args = line["args"]
    assert isinstance(args, dict), line
    return args[name]


def missing_lines(target: str, lines: list[dict[str, object]]) -> set[int]:
    """The statement lines of the function the run's inputs did not cover."""
    module, _, function = target.partition("::")
    path = REPO_ROOT.joinpath(*module.split(".")).with_suffix(".py")
    return set(_function_lines(path, function)) - set(union_of(lines).get(str(path), []))


def _function_lines(path: Path, function: str) -> list[int]:
    """The statement lines of a function's body, by Python's own parse."""
    tree = ast.parse(path.read_text())
    found = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == function
    )
    return [
        node.lineno for line in found.body for node in ast.walk(line) if isinstance(node, ast.stmt)
    ]


def test_the_ticket_s_float_and_bool_flip_each_with_its_expression() -> None:
    lines = lines_of(f"{NESTED}::ratio_and_flags", {"data": {"ratio": 0.5, "flags": [False]}})
    answers = [args_of(line, "data") for line in solved(lines)]
    assert any(type(data["ratio"]) is float and data["ratio"] > 2.5 for data in answers)
    assert any(data["flags"] == [True] for data in answers)
    expressions = [fork["expression"] for line in lines for fork in forks_of(line)]
    assert [">", ["[]", "data", "'ratio'"], 2.5] in expressions
    assert ["[]", ["[]", "data", "'flags'"], 0] in expressions


@pytest.mark.parametrize(
    ("function", "seed"),
    [
        ("flag_item", {"xs": [False]}),
        ("not_flag_item", {"xs": [True]}),
        ("flag_value", {"d": {"k": False}}),
        ("is_true_value", {"d": {"k": False}}),
        ("two_flags", {"d": {"a": False, "b": False}}),
        ("float_item_equal", {"xs": [0.5]}),
        ("float_item_above", {"xs": [0.5]}),
        ("float_value_equal", {"d": {"k": 0.5}}),
        ("float_value_sum", {"d": {"k": 0.5}}),
        ("float_deep", {"d": {"a": [0.5]}}),
        ("mixed_row", {"row": {"age": 0, "name": "", "score": 0.5, "ok": False}}),
        ("grid_row", {"grid": [[0.5], [1]]}),
    ],
)
def test_a_value_inside_flips_and_its_lines_are_covered(function: str, seed: object) -> None:
    target = f"{NESTED}::{function}"
    assert missing_lines(target, lines_of(target, seed)) == set()


def test_a_mixed_row_keeps_each_item_s_kind_on_every_line() -> None:
    lines = lines_of(f"{MIXED}::row_by_position", {"row": [0, 0.5, False]})
    rows = [args_of(line, "row") for line in lines]
    # a flip of a length fork asks for a shorter row, and the items it keeps keep their kinds
    assert all([type(item) for item in row] == [int, float, bool][: len(row)] for row in rows), rows
    assert any(row == [7, row[1], True] and row[1] > 2.5 for row in rows if len(row) == 3), rows


@pytest.mark.parametrize(
    ("function", "seed"),
    [
        ("last_float", {"row": [1, 0.5]}),
        ("last_int", {"row": [0.5, 1]}),
        ("isinstance_guard", {"row": [1, 0.5]}),
        ("added_to_ints", {"xs": [1]}),
    ],
)
def test_a_mixed_list_flips_by_its_kinds(function: str, seed: object) -> None:
    target = f"{MIXED}::{function}"
    uncovered = missing_lines(target, lines_of(target, seed))
    # `added_to_ints` adds a plain 2.5, whose compare has no other side
    assert uncovered == (set() if function != "added_to_ints" else _return_other(target))


def _return_other(target: str) -> set[int]:
    """The line of the last return, which only a plain 2.5 at or below 1.0 reaches."""
    module, _, function = target.partition("::")
    path = REPO_ROOT.joinpath(*module.split(".")).with_suffix(".py")
    return {max(_function_lines(path, function))}


@pytest.mark.parametrize(
    ("function", "seed"),
    [
        ("found", {"xs": [0.5]}),
        ("counted", {"xs": [0.5, 0.5]}),
        ("indexed", {"xs": [0.5, 2.5]}),
        ("equals", {"xs": [0.5, False]}),
        ("total", {"xs": [0.5, 0.5]}),
        ("lowest_highest", {"xs": [0.5, 0.25]}),
        ("first_sorted", {"xs": [0.5, 0.25]}),
        ("sorted_mixed", {"xs": [1, 0.25, True]}),
    ],
)
def test_a_search_a_compare_or_a_sort_over_floats_flips(function: str, seed: object) -> None:
    target = f"{SEARCHES}::{function}"
    lines = lines_of(target, seed)
    assert missing_lines(target, lines) == set()
    # `sorted_mixed`'s last line takes a NaN, since a bool is no float above 2.5
    if function != "sorted_mixed":
        for line in solved(lines):
            items = [item for item in args_of(line, "xs") if isinstance(item, float)]
            assert all(math.isfinite(item) for item in items), line


@pytest.mark.parametrize(
    ("function", "seed"),
    [
        ("after_append", {"xs": [0.5]}),
        ("after_append_argument", {"xs": [0.5], "f": 0.25}),
        ("after_pop", {"xs": [0.5]}),
        ("after_set", {"xs": [0.5]}),
        ("walked_back", {"xs": [0.5, 0.25]}),
        ("sliced", {"xs": [0.5, 0.25]}),
        ("under_tracked_index", {"xs": [0.5, 0.25], "i": 0}),
    ],
)
def test_a_float_flips_through_a_change(function: str, seed: object) -> None:
    target = f"{SEARCHES}::{function}"
    assert missing_lines(target, lines_of(target, seed)) == set()


@pytest.mark.parametrize(
    ("function", "seed"),
    [
        ("get_float", {"d": {"k": 0.5}}),
        ("get_bool", {"d": {"k": False}}),
        ("walk_items", {"d": {"a": 0.5}}),
        ("walk_values", {"d": {"a": False}}),
        ("under_tracked_key", {"table": {"a": 0.5}, "name": "a"}),
        ("annotated_float", {"d": {}}),
        ("annotated_bool", {"d": {}}),
    ],
)
def test_a_dict_s_float_or_bool_value_flips(function: str, seed: object) -> None:
    target = f"{VALUES}::{function}"
    assert missing_lines(target, lines_of(target, seed)) == set()


def test_a_float_under_a_tracked_key_keeps_its_read_as_written() -> None:
    lines = lines_of(f"{VALUES}::under_tracked_key", {"table": {"a": 0.5}, "name": "a"})
    expressions = [fork["expression"] for line in lines for fork in forks_of(line)]
    assert [">", ["[]", "table", "name"], 2.5] in expressions


def test_a_bool_in_a_list_built_on_the_last_row_leaves_other_forks_flipping() -> None:
    # the solver types any row of the grid alike, so core hands the item out under its own place
    lines = solved(lines_of(f"{NESTED}::last_row_flag", {"grid": [[1], [False]], "other": 0}))
    assert any(args_of(line, "other") > 5 for line in lines), lines


def test_a_floor_of_a_float_in_a_list_built_on_a_picked_row_is_rendered() -> None:
    assert solved(lines_of(f"{NESTED}::picked_row_floor", {"grid": [[0.5], [1]], "i": 0}))


@pytest.mark.parametrize(
    ("function", "seed"),
    [
        ("picked_row_above", {"grid": [[0.5], [0.5]], "i": 1}),
        ("picked_row_flag", {"grid": [[False], [False]], "i": 1}),
    ],
)
def test_a_row_an_index_picks_from_rows_of_one_kind_follows_the_index(
    function: str, seed: object
) -> None:
    target = f"{NESTED}::{function}"
    lines = lines_of(target, seed)
    read = ["[]", ["[]", "grid", "i"], 0]
    expressions = [fork["expression"] for line in lines for fork in forks_of(line)]
    assert any(
        read == part for expression in expressions for part in [expression, *_parts(expression)]
    )
    assert all(line["mismatch_at"] is None for line in lines), lines
    assert missing_lines(target, lines) == set()


@pytest.mark.parametrize(
    ("function", "seed"),
    [
        ("picked_row_above", {"grid": [[1], [0.5]], "i": 1}),
        ("cut_item_above", {"xs": [1, 0.5], "i": 1}),
        ("joined_item_above", {"ys": [1], "xs": [0.5, 1]}),
        ("sorted_row_above", {"grid": [[1], [2.5, 0.5]], "i": 1}),
        ("sorted_row_equal", {"grid": [[2.5, 0.5], [1]], "i": 0}),
        ("sorted_row_floor", {"grid": [[2.5, 0.5], [1]], "i": 0}),
        ("sorted_row_is_true", {"grid": [[False, False], [1]], "i": 0}),
        ("sorted_cut_equal", {"xs": [1, 2.5, 0.5]}),
        ("popped_and_sorted", {"xs": [0.5, 2, False]}),
        ("cut_row_above", {"grid": [[0.5], [0.5]], "i": 1}),
        ("keyed_row_above", {"d": {"a": [0.5], "b": [0.5]}, "k": "b"}),
        ("joined_row_above", {"ys": [[1]], "grid": [[0.5], [1]]}),
        ("picked_dict_above", {"rows": [{"x": 0.5}, {"x": 0.5}], "i": 1}),
        ("last_dict_above", {"rows": [{"x": 0.5}, {"x": 0.5}]}),
    ],
)
def test_a_float_or_bool_the_solver_cannot_type_stays_plain_and_is_named(
    function: str, seed: object
) -> None:
    target = f"{NESTED}::{function}"
    result = run_pyct(target, "--args", json.dumps(seed), *QUICK)
    assert result.returncode == 0, result.stderr
    summary = summary_line(result.stdout)
    seed_line = input_lines(result.stdout)[0]
    read_at = _return_line(target, "hit") - 1
    # the seed reads the float or the bool: its fork never reaches the solver, and the run says so
    assert not [fork for fork in forks_of(seed_line) if _tests_the_item(fork, read_at)], seed_line
    assert seed_line["downgrades"], seed_line
    assert summary["stopped"] != "solver failed", summary


@pytest.mark.parametrize(
    ("function", "seed"),
    [
        ("sorted_row_above", {"grid": [[1], [2.5, 0.5]], "i": 1}),
        ("sorted_ints_row", {"grid": [[9, 6], [1, "a"]], "i": 0}),
    ],
)
def test_a_list_of_mixed_rows_covers_what_its_ints_reach(function: str, seed: object) -> None:
    target = f"{NESTED}::{function}"
    assert missing_lines(target, lines_of(target, seed, *QUICK)) == set()


def test_a_long_series_of_appends_reads_its_float() -> None:
    target = f"{NESTED}::long_appended_float"
    result = run_pyct(target, "--args", json.dumps({"xs": [0.5]}), *QUICK)
    assert result.returncode == 0, result.stderr
    assert "RecursionError" not in result.stdout
    assert missing_lines(target, input_lines(result.stdout)) == set()


def _tests_the_item(fork: dict[str, object], read_at: int) -> bool:
    """Whether a fork on the line that tests the item is that test, by what the targets test it
    with, rather than a check on a length or a key."""
    text = json.dumps(fork["expression"])
    return fork["line"] == read_at and any(test in text for test in _ITEM_TESTS)


def _parts(expression: object) -> list[object]:
    """The operands of an expression, none for a leaf."""
    return list(expression[1:]) if isinstance(expression, list) else []


def _return_line(target: str, value: str) -> int:
    """The line of the function's ``return`` of a str literal."""
    module, _, function = target.partition("::")
    path = REPO_ROOT.joinpath(*module.split(".")).with_suffix(".py")
    tree = ast.parse(path.read_text())
    found = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
    return next(
        node.lineno
        for node in ast.walk(found)
        if isinstance(node, ast.Return)
        and isinstance(node.value, ast.Constant)
        and node.value.value == value
    )


def test_a_bool_read_by_is_true_records_the_read_as_its_fork() -> None:
    lines = lines_of(f"{NESTED}::is_true_value", {"d": {"k": False}})
    assert any(args_of(line, "d")["k"] is True for line in solved(lines))


def test_an_ordinary_float_fork_answers_a_finite_item() -> None:
    lines = lines_of(f"{ITEMS}::finite_answer", {"xs": [1.5, 2.5]})
    assert solved(lines)
    for line in lines:
        assert all(math.isfinite(item) for item in args_of(line, "xs")), line


def test_an_item_that_must_be_nan_leaves_another_list_finite() -> None:
    lines = lines_of(f"{ITEMS}::freed_beside", {"xs": [0.5], "ys": [0.5]})
    held = [line for line in lines if args_of(line, "xs") and math.isnan(args_of(line, "xs")[0])]
    assert held
    assert all(math.isfinite(args_of(line, "ys")[0]) for line in held), held


def run_back(target: str, line: dict[str, object]) -> None:
    """The line's ``args`` as a seed, which must run with exit 0."""
    seed = json.dumps(line["args"])
    result = run_pyct(target, "--args", seed)
    assert result.returncode == 0, result.stderr


def test_nan_and_infinity_flip_in_an_item_and_read_back() -> None:
    target = f"{ITEMS}::nan_item"
    lines = solved(lines_of(target, {"xs": [0.5]}))
    assert any(math.isnan(args_of(line, "xs")[0]) for line in lines)
    run_back(target, lines[-1])
    target = f"{ITEMS}::infinite_item"
    lines = solved(lines_of(target, {"xs": [0.5]}))
    assert any(args_of(line, "xs")[0] == math.inf for line in lines)
    run_back(target, lines[-1])


@pytest.mark.parametrize(
    "text",
    ['{"xs": [NaN]}', '{"xs": [-0.0]}', '{"xs": [Infinity]}', '{"xs": [-Infinity]}'],
)
def test_a_seed_of_an_ieee_form_binds_as_that_double(text: str) -> None:
    result = run_pyct(f"{ITEMS}::nan_item", "--args", text)
    assert result.returncode == 0, result.stderr
    assert input_lines(result.stdout)
    # the target's own error carries what it read: repr tells -0.0, NaN and each infinity apart
    result = run_pyct(f"{ITEMS}::raises_what_it_read", "--args", text)
    assert result.returncode == 0, result.stderr
    failure = input_lines(result.stdout)[0]["failure"]
    assert isinstance(failure, dict)
    assert failure["detail"] == f"ValueError: {json.loads(text)['xs'][0]!r}"


@pytest.mark.parametrize(
    ("function", "seed"),
    [("same_list", {"xs": [float("nan")]}), ("searched_itself", {"xs": [float("nan")]})],
)
def test_a_nan_item_is_itself_to_a_list_as_python_says(function: str, seed: object) -> None:
    lines = lines_of(f"{ITEMS}::{function}", seed)
    compares = [fork["expression"] for fork in forks_named(lines, "==")]
    assert all('"[]"' not in json.dumps(compare) for compare in compares), compares
    assert lines[0]["failure"] is None


def forks_named(lines: list[dict[str, object]], head: str) -> list[dict[str, Any]]:
    """The forks of the lines whose expression's head is ``head``."""
    return [
        fork
        for line in lines
        for fork in forks_of(line)
        if isinstance(fork["expression"], list) and fork["expression"][0] == head
    ]


def test_an_empty_seed_fills_a_float_or_bool_from_its_annotation() -> None:
    lines = lines_of(f"{ITEMS}::annotated_list", {"xs": []})
    answers = [args_of(line, "xs") for line in solved(lines)]
    assert [0.0] in answers
    assert [2.5] in answers
    lines = lines_of(f"{ITEMS}::annotated_flags", {"xs": []})
    answers = [args_of(line, "xs") for line in solved(lines)]
    assert [False] in answers
    assert [True] in answers


def test_an_empty_seed_with_no_annotation_fills_null_and_the_flip_misses() -> None:
    lines = lines_of(f"{ITEMS}::no_annotation", {"xs": []})
    assert [args_of(line, "xs") for line in solved(lines)] == [[None]]


def test_a_plain_float_the_target_added_records_no_fork_and_no_downgrade() -> None:
    lines = lines_of(f"{MIXED}::added_to_ints", {"xs": [1]})
    expressions = [json.dumps(fork["expression"]) for line in lines for fork in forks_of(line)]
    assert all("1.0" not in text for text in expressions), expressions
    assert all(not line["downgrades"] for line in lines), lines


@pytest.mark.parametrize(
    "target",
    [
        f"{NESTED}::flag_item",
        f"{NESTED}::not_flag_item",
        f"{NESTED}::flag_value",
        f"{NESTED}::two_flags",
        f"{VALUES}::get_bool",
        f"{VALUES}::walk_values",
    ],
)
def test_a_bool_fixture_legacy_flips_has_no_accepted_difference(target: str) -> None:
    records = [json.loads(line) for line in ACCEPTED.read_text().splitlines()]
    assert target not in {record.get("target") for record in records}


def test_no_fixture_of_this_story_leaves_a_line_only_legacy_covers() -> None:
    modules = (NESTED, MIXED, SEARCHES, VALUES, ITEMS)
    records = [json.loads(line) for line in ACCEPTED.read_text().splitlines()]
    ours = [r for r in records if str(r.get("target")).startswith(modules)]
    assert ours
    assert all(record["only_legacy"] == [] for record in ours), ours
