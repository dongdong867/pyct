"""Acceptance tests for the record-bool-of-a-tracked-list-where-it-is-tested bug.

`bool(items)` on a tracked list is a tracked bool holding the condition `if items:` tests, so its
fork is recorded where the target tests it, as `bool(x)` on a tracked int is. Each test runs pyct
through the command line, since only a run through it substitutes the call written `bool(...)`.
"""

import pytest

from targets.lists import truth_kept
from tests.acceptance.harness import REPO_ROOT, first_line, input_lines, run_pyct, summary_line
from tests.acceptance.test_bools import at
from tests.acceptance.test_ints import forks_of
from tests.acceptance.test_pass_keywords_through_a_downgrade import covered_in
from tests.acceptance.test_read_a_tracked_value_s_type_as_its_base_type import (
    line_of,
    python_raise,
    raised,
)
from tests.acceptance.test_substitute_conversions import downgrade_names

TARGET = "targets.lists.truth_kept"
FILE = REPO_ROOT / "targets" / "lists" / "truth_kept.py"
EMPTY = '{"items": []}'
FILLED = ["!=", ["len", "items"], 0]


def lines_of(function: str) -> tuple[int, int, int]:
    """The `bool` line, the `if ok:` line and the line under it, in one function."""
    return (
        line_of(FILE, "ok = bool(", function),
        line_of(FILE, "if ok:", function),
        line_of(FILE, 'return "filled"', function),
    )


def placed(line: dict[str, object]) -> list[tuple[object, object, object]]:
    """Each fork on a printed line, by its line, its expression and the side it took."""
    return [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(line)]


def took(inputs: list[dict[str, object]], fork: tuple[object, object, object]) -> bool:
    """Whether any of the printed lines took this fork: its line, its expression and its side."""
    return any(fork in placed(line) for line in inputs)


def filled(inputs: list[dict[str, object]]) -> list[dict[str, object]]:
    """The input lines whose `items` holds anything."""
    found = []
    for line in inputs:
        args = line["args"]
        assert isinstance(args, dict), line
        if args["items"]:
            found.append(line)
    return found


def seed_fork_line(stderr: str, number: int) -> str:
    """The seed's stderr fork line at a line of the fixture: the first, since the seed runs
    first."""
    found = [line for line in stderr.splitlines() if line.startswith(f"fork {FILE}:{number}:")]
    assert found, stderr
    return found[0]


# record-bool-of-a-tracked-list-where-it-is-tested-records-at-the-test
@pytest.mark.parametrize("where", [(), ("--in-process",)], ids=["own-process", "in-process"])
def test_records_at_the_test(where: tuple[str, ...]) -> None:
    result = run_pyct(f"{TARGET}::kept", EMPTY, "--budget", "10", *where)

    assert result.returncode == 0, result.stderr
    called, tested, under = lines_of("kept")
    inputs = input_lines(result.stdout)
    seed = inputs[0]
    assert at(seed, called) == []
    assert placed(seed) == [(tested, FILLED, False)]
    assert seed_fork_line(result.stderr, tested).endswith("  len(items) != 0  not taken")
    solved = filled(inputs[1:])
    assert solved, inputs
    assert all(at(line, tested) == [FILLED] for line in solved)
    assert took(solved, (tested, FILLED, True))
    assert any(under in covered_in(line, str(FILE)) for line in solved)
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# record-bool-of-a-tracked-list-where-it-is-tested-writes-a-changed-list-as-built
def test_writes_a_changed_list_as_built() -> None:
    result = run_pyct(f"{TARGET}::changed_before", EMPTY, "--budget", "10")

    assert result.returncode == 0, result.stderr
    called, tested, _ = lines_of("changed_before")
    seed = first_line(result.stdout)
    built = ["!=", ["len", ["+", "items", ["[,]", 0]]], 0]
    assert at(seed, called) == []
    assert placed(seed) == [(tested, built, True)]
    assert any(
        line.startswith(f"missed {FILE}:{tested}:") and line.endswith(" unsat")
        for line in result.stderr.splitlines()
    ), result.stderr


# record-bool-of-a-tracked-list-where-it-is-tested-keeps-the-list-as-it-was-at-the-call
def test_keeps_the_list_as_it_was_at_the_call() -> None:
    result = run_pyct(f"{TARGET}::changed_after", EMPTY, "--budget", "10")

    assert result.returncode == 0, result.stderr
    called, tested, _ = lines_of("changed_after")
    inputs = input_lines(result.stdout)
    seed = inputs[0]
    assert at(seed, called) == []
    assert placed(seed) == [(tested, FILLED, False)]
    solved = filled(inputs[1:])
    assert solved, inputs
    assert took(solved, (tested, FILLED, True))


# record-bool-of-a-tracked-list-where-it-is-tested-names-a-list-inside-as-indexed
def test_names_a_list_inside_as_indexed() -> None:
    result = run_pyct(f"{TARGET}::inside", '{"grid": [[]]}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    called, tested, _ = lines_of("inside")
    inputs = input_lines(result.stdout)
    seed = inputs[0]
    row = ["!=", ["len", ["[]", "grid", 0]], 0]
    assert placed(seed) == [
        (called, [">", ["len", "grid"], 0], True),
        (tested, row, False),
    ]
    assert seed_fork_line(result.stderr, tested).endswith("  len(grid[0]) != 0  not taken")
    assert took(inputs[1:], (tested, row, True))


# record-bool-of-a-tracked-list-where-it-is-tested-downgrades-a-list-changed-outside
def test_downgrades_a_list_changed_outside() -> None:
    assert truth_kept.pushed([]) == "filled"
    result = run_pyct(f"{TARGET}::pushed", EMPTY, "--budget", "10")

    assert result.returncode == 0, result.stderr
    called, tested, under = lines_of("pushed")
    seed = first_line(result.stdout)
    assert at(seed, called) == [] and at(seed, tested) == []
    assert downgrade_names(seed) == [("__bool__", 1)]
    assert under in covered_in(seed, str(FILE))


# record-bool-of-a-tracked-list-where-it-is-tested-refuses-two-arguments-as-python-does
def test_refuses_two_arguments_as_python_does() -> None:
    error = python_raise(lambda: truth_kept.two_arguments([]))
    assert isinstance(error, TypeError)
    result = run_pyct(f"{TARGET}::two_arguments", EMPTY, "--budget", "10")

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    raised(seed, error)
    assert seed["forks"] == []
    assert seed["downgrades"] == []
