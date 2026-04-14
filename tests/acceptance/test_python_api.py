"""Acceptance tests for the Python API contract (behavior 16)."""


def test_run_concolic_returns_result_with_expected_fields():
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
    """Zero-arg functions should accept empty initial_args."""
    from pyct import run_concolic

    def constant() -> int:
        return 42

    result = run_concolic(target=constant, initial_args={})

    assert result is not None
    assert result.paths_explored >= 1


def test_run_concolic_captures_target_exception_in_error_field():
    """When the target raises, the result should report the error
    rather than propagating the exception to the caller."""
    from pyct import run_concolic

    def always_raises(x: int) -> int:
        raise RuntimeError("boom")

    result = run_concolic(target=always_raises, initial_args={"x": 0})

    # Result is still returned; error path is visible via either the
    # `error` field or `success=False`.
    assert result is not None
    assert result.error is not None or result.success is False
