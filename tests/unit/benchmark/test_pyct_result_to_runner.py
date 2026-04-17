"""``_pyct_result_to_runner`` reconciles success flag with error field.

The engine sets ``success=True`` whenever the exploration loop exited
cleanly and independently stamps ``error`` with the most recent
per-iteration exception (e.g. JSONDecodeError from one of the LLM
seeds). Propagating both verbatim into ``RunnerResult`` yields the
confusing "success=True, error='JSONDecodeError...'" rows seen in
117+ realworld/library observations. The runner normalizes this by
blanking ``error`` whenever the overall run succeeded.
"""

from __future__ import annotations

import pytest
from tools.benchmark.runners import _pyct_result_to_runner
from tools.benchmark.targets import BenchmarkTarget

from pyct.engine.result import RunConcolicResult


@pytest.fixture
def target() -> BenchmarkTarget:
    return BenchmarkTarget(
        name="classify",
        module="tests.unit.benchmark._fixtures.branching_target",
        function="classify",
        initial_args={"x": 0, "y": 0},
    )


def _result(success: bool, error: str | None) -> RunConcolicResult:
    return RunConcolicResult(
        success=success,
        coverage_percent=0.0,
        executed_lines=frozenset({8}),
        paths_explored=0,
        inputs_generated=(),
        iterations=1,
        termination_reason="exhausted" if success else "error",
        error=error,
    )


def test_success_true_with_engine_error_blanks_error(target):
    """success=True means overall exploration completed. A per-iteration
    exception captured in `error` is an infra detail — stripping it at
    the runner layer avoids misleading "success with error" JSON rows.
    """
    result = _result(success=True, error="JSONDecodeError: Expecting value: line 1 column 1")

    runner_result = _pyct_result_to_runner(result, target, elapsed=1.0)

    assert runner_result.success is True
    assert runner_result.error is None


def test_success_false_preserves_engine_error(target):
    """When success=False the error is load-bearing and must pass through."""
    result = _result(success=False, error="child exceeded wall-clock timeout of 110.0s")

    runner_result = _pyct_result_to_runner(result, target, elapsed=1.0)

    assert runner_result.success is False
    assert runner_result.error == "child exceeded wall-clock timeout of 110.0s"


def test_success_true_with_none_error_stays_none(target):
    """No-error clean run is unchanged."""
    result = _result(success=True, error=None)

    runner_result = _pyct_result_to_runner(result, target, elapsed=1.0)

    assert runner_result.success is True
    assert runner_result.error is None
