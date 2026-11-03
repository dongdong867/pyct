"""A `%` format with a tracked operand it has no form for, an int under `%x`, a float under `%s` or
`%.1f`, anything under `%r` or `%a`, a list or a dict under `%s`, makes its whole result plain, as
base does, and names a `__mod__` downgrade (plan nested-floats-bools, 5.10). No fork then reads
the result, so the run asks nothing it cannot answer: no crash, no false unsat, no timeout. A
line that costs is a named loss, and an answer may leave the plan, reported as on base."""

import json

import pytest

from tests.acceptance.harness import input_lines, run_pyct, summary_line
from tests.acceptance.test_nested_floats_and_bools import QUICK, missing_lines, return_line

PLAIN = "targets.nested.turned_plain"


def run(function: str, seed: object, *argv: str) -> tuple[list[dict[str, object]], dict]:
    """A run's input lines and its summary; the run must end with exit 0 and raise nothing of
    pyct's own."""
    result = run_pyct(f"{PLAIN}::{function}", "--args", json.dumps(seed), *argv)
    assert result.returncode == 0, result.stderr
    assert "Traceback" not in result.stderr, result.stderr
    return input_lines(result.stdout), summary_line(result.stdout)


def downgrades(lines: list[dict[str, object]]) -> set[str]:
    """The name of each downgrade the run's lines list."""
    named = [entry for line in lines for entry in line["downgrades"]]  # pyrefly: ignore[not-iterable]
    return {entry["name"] for entry in named}


def solver(summary: dict, answer: str) -> int:
    """How many asks the run's solver answered so."""
    return summary["solver"][answer]


@pytest.mark.parametrize(
    ("function", "seed"),
    [
        # characters past the solver's last, which no program can hold
        ("repr_beside_a_number", {"s": "\U000e0001", "y": 0}),
        ("ascii_beside_a_number", {"s": "\U00030000", "y": 0}),
    ],
)
def test_a_text_the_solver_cannot_hold_asks_nothing(function: str, seed: object) -> None:
    lines, summary = run(function, seed, *QUICK)

    assert "__mod__" in downgrades(lines)
    assert summary["stopped"] == "no fork to flip", summary


@pytest.mark.parametrize(
    ("function", "seed"),
    [
        ("list_beside_a_number", {"xs": [1], "y": 0}),
        ("dict_beside_a_number", {"d": {"k": 1}, "y": 0}),
    ],
)
def test_a_container_written_with_s_is_never_proved_unreachable(
    function: str, seed: object
) -> None:
    lines, summary = run(function, seed, *QUICK)

    assert solver(summary, "unsat") == 0, summary
    assert "__mod__" in downgrades(lines)


@pytest.mark.parametrize(
    ("function", "seed"),
    [
        ("hex_as_a_key", {"d": {"a|0": 1}, "x": 1, "y": 0}),
        ("hex_matched_by_a_walk", {"d": {"q": 1}, "x": 1, "y": 0}),
    ],
)
def test_a_plain_result_used_as_a_key_covers_what_base_covers(function: str, seed: object) -> None:
    lines, _ = run(function, seed, *QUICK)

    assert missing_lines(f"{PLAIN}::{function}", lines) == set()


@pytest.mark.parametrize(
    ("function", "seed"),
    [
        ("hex_that_ends", {"x": 1, "y": 0}),
        ("float_that_ends", {"x": 0.5, "y": 0}),
        ("item_that_ends", {"xs": [0.5], "y": 0}),
    ],
)
def test_a_plain_result_s_end_asks_nothing_that_times_out(function: str, seed: object) -> None:
    lines, summary = run(function, seed, "--budget", "4")

    assert solver(summary, "timeout") == 0, summary
    assert summary["stopped"] == "no fork to flip", summary
    assert "__mod__" in downgrades(lines)


@pytest.mark.parametrize(
    ("function", "seed", "written"),
    [
        ("hex_beside_a_number", {"x": 1, "y": 0}, "hex"),
        ("precision_beside_a_name", {"xs": [0.5], "name": "a"}, "written"),
    ],
)
def test_a_format_beside_a_tracked_value_is_never_proved_unreachable(
    function: str, seed: object, written: str
) -> None:
    lines, summary = run(function, seed, *QUICK)

    assert solver(summary, "unsat") == 0, summary
    # a fork that reads no format, `x > 3` say, flips as it would without one
    target = f"{PLAIN}::{function}"
    assert missing_lines(target, lines) == {return_line(target, written)}
    assert "__mod__" in downgrades(lines)


@pytest.mark.parametrize(
    ("function", "name"), [("text_as_a_key", "__str__"), ("percent_as_a_key", "__mod__")]
)
def test_a_plain_text_as_a_key_is_a_named_loss_whose_answer_may_leave_the_plan(
    function: str, name: str
) -> None:
    lines, _ = run(function, {"d": {"1.5": 1}, "xs": [1.5]}, *QUICK)

    assert name in downgrades(lines)
    assert any(line["mismatch_at"] is not None for line in lines)


@pytest.mark.parametrize(
    ("function", "seed"),
    [
        ("compare_as_an_index", {"ys": [0, 1], "xs": [1]}),
        ("int_of_a_char_as_an_index", {"ys": [0, 1], "s": "0"}),
        ("difference_as_an_index", {"ys": [0, 1], "y": 1, "flags": [True]}),
    ],
)
def test_a_value_used_as_an_index_keeps_its_forks(function: str, seed: object) -> None:
    lines, _ = run(function, seed, *QUICK)

    assert missing_lines(f"{PLAIN}::{function}", lines) == set()


def test_a_value_read_again_and_again_stays_fast() -> None:
    lines, _ = run("flag_read_again_and_again", {"ys": [0, 1], "flags": [False]}, "--budget", "10")

    assert missing_lines(f"{PLAIN}::flag_read_again_and_again", lines) == set()
