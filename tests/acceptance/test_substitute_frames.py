"""Acceptance tests for the frames substitution leaves: recursion runs as deep as written.

Substituted code must not change what plain code does, so a call whose callee is the target's
own, and an operator whose right side is not tracked, run with no frame of pyct's between
the target's frames, and recursion reaches the depth it reaches in plain Python. Each test
spawns ``python -P -m pyct`` through the harness, as only a run through the command line
substitutes.
"""

import pytest

from tests.acceptance.harness import first_line, run_pyct
from tests.acceptance.test_bools import failure_of

RECURSION = "targets.intercept.recursion"


# intercept-builtin-functions-behaves-as-written-on-plain-operands: a recursion 700 deep through
# a method, a module's own `int` and a reflected `+` beside a float literal returns, as in Python
@pytest.mark.parametrize("function", ["deep_find", "deep_own_int", "deep_radd"])
def test_recursion_runs_as_deep_as_in_plain_python(function: str) -> None:
    result = run_pyct(f"{RECURSION}::{function}", '{"x": 4}')

    assert result.returncode == 0, result.stderr
    assert first_line(result.stdout)["failure"] is None, result.stdout


# intercept-builtin-functions-leaves-a-builtins-raise-to-the-target: recursion without end
# through `int(...)` is the target's
def test_endless_recursion_through_a_conversion_is_the_target_s() -> None:
    result = run_pyct("targets.intercept.endless::conv", '{"x": 0}')

    assert result.returncode == 0, result.stderr
    failure = failure_of(first_line(result.stdout))
    assert failure["kind"] == "target_raised", failure
    assert str(failure["detail"]).startswith("RecursionError")


# intercept-builtin-functions-leaves-a-builtins-raise-to-the-target: Python's own operator
# refusing a float literal and a tracked int is the target's raise
@pytest.mark.parametrize(
    ("function", "seed", "error"),
    [("shift", '{"n": 0}', "TypeError"), ("power", '{"n": 400}', "OverflowError")],
)
def test_python_s_own_operator_refusing_a_handed_operand_is_the_target_s(
    function: str, seed: str, error: str
) -> None:
    result = run_pyct(f"targets.intercept.handed_raises::{function}", seed)

    assert result.returncode == 0, result.stderr
    failure = failure_of(first_line(result.stdout))
    assert failure["kind"] == "target_raised", failure
    assert str(failure["detail"]).startswith(error)
