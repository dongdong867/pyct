"""A tracked value whose text `%` writes into a result that stays tracked is held at its value in
each ask whose path reads that result (plan nested-floats-bools, 5.9): no answer changes the
value the result already wrote, and an unsat that rests on it is no proof that the path is
unreachable. A result that goes wholly plain holds nothing, and an answer may leave the plan
there, as on base. A line either costs is a named loss."""

import json

import pytest

from tests.acceptance.harness import input_lines, run_pyct, summary_line
from tests.acceptance.test_nested_floats_and_bools import QUICK, missing_lines, return_line

PLAIN = "targets.nested.turned_plain"


def run(function: str, seed: object, *argv: str) -> tuple[list[dict[str, object]], dict]:
    """A run's input lines and its summary; the run must end with exit 0."""
    result = run_pyct(f"{PLAIN}::{function}", "--args", json.dumps(seed), *argv)
    assert result.returncode == 0, result.stderr
    return input_lines(result.stdout), summary_line(result.stdout)


def downgrades(lines: list[dict[str, object]]) -> set[str]:
    """The name of each downgrade the run's lines list."""
    named = [entry for line in lines for entry in line["downgrades"]]  # pyrefly: ignore[not-iterable]
    return {entry["name"] for entry in named}


@pytest.mark.parametrize(
    ("function", "seed", "written"),
    [
        ("hex_beside_a_number", {"x": 1, "y": 0}, "hex"),
        ("precision_beside_a_name", {"xs": [0.5], "name": "a"}, "written"),
    ],
)
def test_a_value_written_into_a_format_is_never_proved_unreachable(
    function: str, seed: object, written: str
) -> None:
    lines, summary = run(function, seed, *QUICK)

    assert summary["solver"]["unsat"] == 0, summary  # pyrefly: ignore[bad-index]
    # a fork that reads no format, `x > 3` say, flips as it would without one
    target = f"{PLAIN}::{function}"
    missing = missing_lines(target, lines)
    assert missing <= {return_line(target, written)}
    if missing:
        assert "__mod__" in downgrades(lines)


@pytest.mark.parametrize(
    ("function", "name"), [("text_as_a_key", "__str__"), ("percent_as_a_key", "__mod__")]
)
def test_a_value_written_wholly_plain_holds_nothing_and_its_answer_may_leave_the_plan(
    function: str, name: str
) -> None:
    lines, _ = run(function, {"d": {"1.5": 1}, "xs": [1.5]}, *QUICK)

    assert name in downgrades(lines)
    assert any(line["mismatch_at"] is not None for line in lines)


def test_a_value_used_wholly_plain_as_an_index_keeps_its_forks() -> None:
    lines, _ = run("compare_as_an_index", {"ys": [0, 1], "xs": [1]}, *QUICK)

    assert missing_lines(f"{PLAIN}::compare_as_an_index", lines) == set()


def test_a_value_read_again_and_again_stays_fast() -> None:
    lines, _ = run("flag_read_again_and_again", {"ys": [0, 1], "flags": [False]}, "--budget", "10")

    assert missing_lines(f"{PLAIN}::flag_read_again_and_again", lines) == set()
