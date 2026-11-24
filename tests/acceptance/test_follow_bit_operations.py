"""Acceptance tests for follow-bit-operations, through the command line."""

import pytest

from tests.acceptance.harness import (
    REPO_ROOT,
    downgrade,
    input_lines,
    one_line,
    run_pyct,
    union_of,
)

FILE = str(REPO_ROOT / "targets" / "ints" / "bit_fields.py")
AT = "targets/ints/bit_fields.py"


def _target(name: str) -> str:
    return f"targets.ints.bit_fields::{name}"


def _downgrades(lines: list[dict[str, object]]) -> list[object]:
    return [each for line in lines for each in line["downgrades"]]  # pyrefly: ignore[not-iterable]


# follow-bit-operations-the-ticket-s-probe-covers-every-line-without-the-llm
def test_the_ticket_s_probe_covers_every_line_without_the_llm() -> None:
    result = run_pyct(_target("field"), '{"n": 0}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    # every line of the body; the def ran at import, under no input
    assert union_of(lines) == {FILE: [2, 3, 4, 5, 6]}
    assert _downgrades(lines) == []


# follow-bit-operations-each-operator-with-a-constant-is-followed-with-python-s-result
def test_each_operator_with_a_constant_is_followed_either_way_round_and_augmented() -> None:
    result = run_pyct(_target("each_operator"), '{"n": 0}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    # every return is reached: the solver answered each condition with an int that takes it,
    # negative ones among them, as Python computes it
    assert union_of(lines) == {FILE: list(range(10, 22))}
    assert _downgrades(lines) == []


# follow-bit-operations-two-tracked-ints-meet-in-and-or-xor
def test_two_tracked_ints_meet_in_and_and_xor() -> None:
    result = run_pyct(_target("two_masks"), '{"x": 0, "y": 0}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert union_of(lines) == {FILE: list(range(25, 30))}
    assert _downgrades(lines) == []


# follow-bit-operations-what-stays-a-downgrade
def test_a_shift_by_a_tracked_count_and_a_bool_s_shift_stay_downgrades() -> None:
    result = run_pyct(_target("still_lost"), '{"n": 0, "b": false}')

    assert result.returncode == 0, result.stderr
    line = one_line(result.stdout)
    assert line["downgrades"] == [
        downgrade("__rlshift__", 1, f"{AT}:33:7"),
        downgrade("__lshift__", 1, f"{AT}:35:7"),
    ]
    assert line["forks"] == []


# follow-bit-operations-a-shift-by-a-negative-count-raises-as-python-does
def test_a_shift_by_a_negative_count_raises_as_python_does() -> None:
    result = run_pyct(_target("negative_count"), '{"n": 3}')

    assert result.returncode == 0, result.stderr
    line = one_line(result.stdout)
    with pytest.raises(ValueError) as plain:
        _ = 3 << -1
    assert line["failure"] == {"kind": "target_raised", "detail": f"ValueError: {plain.value}"}
