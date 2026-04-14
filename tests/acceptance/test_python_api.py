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
