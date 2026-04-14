"""Acceptance tests for the Python API contract (behavior 16)."""


def test_run_concolic_returns_result_with_expected_fields():
    """
    Given the top-level run_concolic API and a trivial target
    When the caller invokes it with an initial args dict
    Then the return value should be a RunConcolicResult instance
      And expose the documented fields: success, coverage_percent,
          executed_lines, paths_explored, inputs_generated, iterations, error
    """
    from pyct import RunConcolicResult, run_concolic

    def trivial(x: int) -> int:
        if x > 0:
            return 1
        return 0

    result = run_concolic(target=trivial, initial_args={"x": 0})

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
    When run_concolic is invoked with an empty initial_args dict
    Then the engine should accept the call without complaining about args
      And at least one path should be recorded
    """
    from pyct import run_concolic

    def constant() -> int:
        return 42

    result = run_concolic(target=constant, initial_args={})

    assert result.success
    assert result.paths_explored >= 1


def test_run_concolic_captures_target_exception_in_error_field():
    """
    Given a target that always raises RuntimeError
    When run_concolic is invoked on it
    Then the exception should NOT propagate out of run_concolic
      And the result should report the failure via error field or success=False
    """
    from pyct import run_concolic

    def always_raises(x: int) -> int:
        raise RuntimeError("boom")

    result = run_concolic(target=always_raises, initial_args={"x": 0})

    # The exception should be captured, not propagated — verify the
    # failure is surfaced via either error or success flag.
    assert result.error is not None or result.success is False
