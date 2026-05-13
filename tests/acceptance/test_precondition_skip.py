"""Acceptance tests for icontract precondition short-circuit during exploration."""

from __future__ import annotations

import icontract

from pyct import run_concolic


def test_run_concolic_skips_target_body_when_require_returns_false() -> None:
    """
    Given a target decorated with @icontract.require(lambda x: x > 0)
    When run_concolic explores it with initial_args={"x": -1}
    Then the target body must not execute
    And result.preconditions_violated must be 1
    And termination_reason must not be "timeout"
    """
    body_calls: list[int] = []

    @icontract.require(lambda x: x > 0, description="x must be positive")
    def target(x: int) -> int:
        body_calls.append(x)
        return x * 2

    result = run_concolic(target=target, initial_args={"x": -1}, isolated=False)

    assert result.success
    assert body_calls == [], (
        f"target body invoked despite failing precondition: {body_calls}"
    )
    assert result.preconditions_violated == 1
    assert result.termination_reason != "timeout"
