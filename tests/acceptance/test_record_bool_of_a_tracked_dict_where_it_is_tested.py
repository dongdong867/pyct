"""Acceptance tests for the record-bool-of-a-tracked-dict-where-it-is-tested bug.

`bool(config)` on a tracked dict, or on one of its views, is a tracked bool holding the condition
`if config:` tests, so its fork is recorded where the target tests it, as `bool(x)` on a tracked
int is. Each test runs pyct through the command line, since only a run through it substitutes the
call written `bool(...)`.
"""

import pytest

from targets.dicts import truth_kept
from tests.acceptance.harness import (
    REPO_ROOT,
    first_line,
    input_lines,
    lines_expressions_and_sides,
    run_pyct,
    summary_line,
    took,
)
from tests.acceptance.test_bools import at
from tests.acceptance.test_pass_keywords_through_a_downgrade import covered_in
from tests.acceptance.test_read_a_tracked_value_s_type_as_its_base_type import (
    line_of,
    python_raise,
    raised,
)
from tests.acceptance.test_substitute_conversions import downgrade_names

TARGET = "targets.dicts.truth_kept"
FILE = REPO_ROOT / "targets" / "dicts" / "truth_kept.py"
EMPTY = '{"config": {}}'
FILLED = ["!=", ["len", "config"], 0]


def lines_of(function: str) -> tuple[int, int, int]:
    """The `bool` line, the `if ok:` line and the line under it, in one function."""
    return (
        line_of(FILE, "ok = bool(", function),
        line_of(FILE, "if ok:", function),
        line_of(FILE, 'return "filled"', function),
    )


def filled(inputs: list[dict[str, object]]) -> list[dict[str, object]]:
    """The input lines whose `config` holds anything."""
    found = []
    for line in inputs:
        args = line["args"]
        assert isinstance(args, dict), line
        if args["config"]:
            found.append(line)
    return found


def seed_fork_line(stderr: str, number: int) -> str:
    """The seed's stderr fork line at a line of the fixture: the first, since the seed runs
    first."""
    found = [line for line in stderr.splitlines() if line.startswith(f"fork {FILE}:{number}:")]
    assert found, stderr
    return found[0]


# record-bool-of-a-tracked-dict-where-it-is-tested-records-at-the-test
@pytest.mark.parametrize("where", [(), ("--in-process",)], ids=["own-process", "in-process"])
def test_records_at_the_test(where: tuple[str, ...]) -> None:
    result = run_pyct(f"{TARGET}::kept", EMPTY, "--budget", "10", *where)

    assert result.returncode == 0, result.stderr
    called, tested, under = lines_of("kept")
    inputs = input_lines(result.stdout)
    seed = inputs[0]
    assert at(seed, called) == []
    assert lines_expressions_and_sides(seed) == [(tested, FILLED, False)]
    assert seed_fork_line(result.stderr, tested).endswith("  len(config) != 0  not taken")
    solved = filled(inputs[1:])
    assert solved, inputs
    assert all(at(line, tested) == [FILLED] for line in solved)
    assert took(solved, (tested, FILLED, True))
    assert any(under in covered_in(line, str(FILE)) for line in solved)
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# record-bool-of-a-tracked-dict-where-it-is-tested-writes-a-changed-dict-by-its-size
def test_writes_a_changed_dict_by_its_size() -> None:
    result = run_pyct(f"{TARGET}::changed_before", EMPTY, "--budget", "10")

    assert result.returncode == 0, result.stderr
    called, tested, _ = lines_of("changed_before")
    seed = first_line(result.stdout)
    grown = ["!=", ["+", ["len", "config"], 1], 0]
    stored = line_of(FILE, 'config["a"] = 0', "changed_before")
    assert at(seed, called) == []
    # the store records its own lookup where it runs
    assert lines_expressions_and_sides(seed) == [
        (stored, ["in", "'a'", "config"], False),
        (tested, grown, True),
    ]
    assert any(
        line.startswith(f"missed {FILE}:{tested}:") and line.endswith(" unsat")
        for line in result.stderr.splitlines()
    ), result.stderr


# record-bool-of-a-tracked-dict-where-it-is-tested-keeps-the-dict-as-it-was-at-the-call
def test_keeps_the_dict_as_it_was_at_the_call() -> None:
    result = run_pyct(f"{TARGET}::changed_after", EMPTY, "--budget", "10")

    assert result.returncode == 0, result.stderr
    called, tested, _ = lines_of("changed_after")
    inputs = input_lines(result.stdout)
    seed = inputs[0]
    stored = line_of(FILE, 'config["b"] = 1', "changed_after")
    assert at(seed, called) == []
    assert lines_expressions_and_sides(seed) == [
        (stored, ["in", "'b'", "config"], False),
        (tested, FILLED, False),
    ]
    solved = filled(inputs[1:])
    assert solved, inputs
    assert took(solved, (tested, FILLED, True))


# record-bool-of-a-tracked-dict-where-it-is-tested-names-a-dict-inside-by-its-key
def test_names_a_dict_inside_by_its_key() -> None:
    result = run_pyct(f"{TARGET}::inside", '{"cfg": {"a": {}}}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    called, tested, _ = lines_of("inside")
    inputs = input_lines(result.stdout)
    seed = inputs[0]
    row = ["!=", ["len", ["[]", "cfg", "'a'"]], 0]
    assert lines_expressions_and_sides(seed) == [
        (called, ["in", "'a'", "cfg"], True),
        (tested, row, False),
    ]
    assert seed_fork_line(result.stderr, tested).endswith("  len(cfg['a']) != 0  not taken")
    assert took(inputs[1:], (tested, row, True))


# record-bool-of-a-tracked-dict-where-it-is-tested-records-a-view-at-the-test
@pytest.mark.parametrize("view", ["keys", "values", "items"])
def test_records_a_view_at_the_test(view: str) -> None:
    result = run_pyct(f"{TARGET}::{view}", EMPTY, "--budget", "10")

    assert result.returncode == 0, result.stderr
    called, tested, _ = lines_of(view)
    inputs = input_lines(result.stdout)
    seed = inputs[0]
    assert at(seed, called) == []
    assert lines_expressions_and_sides(seed) == [(tested, FILLED, False)]
    solved = filled(inputs[1:])
    assert solved, inputs
    assert took(solved, (tested, FILLED, True))


# record-bool-of-a-tracked-dict-where-it-is-tested-downgrades-a-dict-changed-outside
def test_downgrades_a_dict_changed_outside() -> None:
    assert truth_kept.stored_outside({}) == "filled"
    result = run_pyct(f"{TARGET}::stored_outside", EMPTY, "--budget", "10")

    assert result.returncode == 0, result.stderr
    called, tested, under = lines_of("stored_outside")
    seed = first_line(result.stdout)
    assert at(seed, called) == [] and at(seed, tested) == []
    assert downgrade_names(seed) == [("__bool__", 1)]
    assert under in covered_in(seed, str(FILE))


# record-bool-of-a-tracked-dict-where-it-is-tested-refuses-two-arguments-as-python-does
def test_refuses_two_arguments_as_python_does() -> None:
    error = python_raise(lambda: truth_kept.two_arguments({}))
    assert isinstance(error, TypeError)
    result = run_pyct(f"{TARGET}::two_arguments", EMPTY, "--budget", "10")

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    raised(seed, error)
    assert seed["forks"] == []
    assert seed["downgrades"] == []
