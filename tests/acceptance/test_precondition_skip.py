"""Acceptance tests for icontract precondition short-circuit during exploration."""

from __future__ import annotations


def test_run_concolic_skips_target_body_when_require_returns_false() -> None:
    """
    Given a target decorated with @icontract.require(lambda x: x > 0)
    When run_concolic explores it with initial_args={"x": -1}
    Then the target body must not execute
    And result.preconditions_violated must be 1
    And termination_reason must not be "timeout"
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.contracts import basic

    basic.PRECONDITION_BODY_CALLS.clear()

    result = run_concolic(
        target=basic.precondition_skip_target,
        initial_args={"x": -1},
        isolated=False,
    )

    assert result.success
    assert basic.PRECONDITION_BODY_CALLS == [], (
        f"target body invoked despite failing precondition: {basic.PRECONDITION_BODY_CALLS}"
    )
    assert result.preconditions_violated == 1
    assert result.termination_reason != "timeout"
