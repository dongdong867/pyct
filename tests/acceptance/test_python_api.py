"""Acceptance tests for the Python API contract (behavior 16).

These tests exercise the engine directly via ``Engine.explore`` rather
than the public ``run_concolic`` wrapper. The wrapper defaults to
``isolated=True`` which runs the target in a subprocess, and inline
functions defined inside a test body cannot be pickled into that
subprocess. Using ``Engine`` directly keeps the test targets inline
and focused on the API surface under test.
"""

from pyct import Engine, ExecutionConfig, RunConcolicResult
from pyct.engine.result import ExplorationResult


def test_run_concolic_returns_result_with_expected_fields():
    """
    Given the top-level API and a trivial target
    When the caller invokes Engine.explore with an initial args dict
    Then the exploration result should expose the documented fields
      And wrap cleanly into a RunConcolicResult via from_exploration
    """

    def trivial(x: int) -> int:
        if x > 0:
            return 1
        return 0

    engine = Engine(ExecutionConfig())
    exploration = engine.explore(trivial, {"x": 0})
    result = RunConcolicResult.from_exploration(exploration, list(exploration.inputs_generated))

    assert isinstance(exploration, ExplorationResult)
    assert isinstance(result, RunConcolicResult)
    assert hasattr(result, "success")
    assert hasattr(result, "coverage_percent")
    assert hasattr(result, "executed_lines")
    assert hasattr(result, "paths_explored")
    assert hasattr(result, "inputs_generated")
    assert hasattr(result, "iterations")
    assert hasattr(result, "error")


def test_run_concolic_with_empty_args_for_zero_arg_function():
    """
    Given a zero-argument target function
    When Engine.explore is invoked with an empty initial_args dict
    Then the engine should accept the call without complaining about args
      And at least one path should be recorded
    """

    def constant() -> int:
        return 42

    engine = Engine(ExecutionConfig())
    result = engine.explore(constant, {})

    assert result.success
    assert result.paths_explored >= 1


def test_run_concolic_captures_target_exception_in_error_field():
    """
    Given a target that always raises RuntimeError
    When Engine.explore is invoked on it
    Then the exception should NOT propagate out of explore
      And the result should report the failure via error field or success=False
    """

    def always_raises(x: int) -> int:
        raise RuntimeError("boom")

    engine = Engine(ExecutionConfig())
    result = engine.explore(always_raises, {"x": 0})

    assert result.error is not None or result.success is False
