"""Unit tests for ExplorationResult and RunConcolicResult."""

import pytest

from pyct.engine.result import ExplorationResult, RunConcolicResult


def _make_exploration_result(
    success: bool = True,
    coverage_percent: float = 0.0,
    executed_lines: frozenset[int] = frozenset(),
    paths_explored: int = 0,
    iterations: int = 0,
    termination_reason: str = "",
    elapsed_seconds: float = 0.0,
    error: str | None = None,
) -> ExplorationResult:
    return ExplorationResult(
        success=success,
        coverage_percent=coverage_percent,
        executed_lines=executed_lines,
        paths_explored=paths_explored,
        iterations=iterations,
        termination_reason=termination_reason,
        elapsed_seconds=elapsed_seconds,
        error=error,
    )


class TestExplorationResult:
    def test_successful_result_fields(self):
        result = _make_exploration_result(
            success=True,
            coverage_percent=95.0,
            executed_lines=frozenset({1, 2, 3, 4}),
            paths_explored=5,
            iterations=10,
            termination_reason="full_coverage",
            elapsed_seconds=0.5,
        )
        assert result.success is True
        assert result.coverage_percent == 95.0
        assert result.executed_lines == frozenset({1, 2, 3, 4})
        assert result.paths_explored == 5
        assert result.iterations == 10
        assert result.termination_reason == "full_coverage"
        assert result.elapsed_seconds == 0.5
        assert result.error is None

    def test_failed_result_includes_error_message(self):
        result = _make_exploration_result(
            success=False,
            termination_reason="error",
            error="Solver crashed",
        )
        assert result.success is False
        assert result.error == "Solver crashed"

    def test_result_is_frozen(self):
        result = _make_exploration_result()
        with pytest.raises((AttributeError, TypeError)):
            result.success = False  # type: ignore


class TestRunConcolicResult:
    def test_run_result_has_inputs_generated(self):
        result = RunConcolicResult(
            success=True,
            coverage_percent=95.0,
            executed_lines=frozenset({1, 2}),
            paths_explored=3,
            inputs_generated=({"x": 1}, {"x": 2}),
            iterations=5,
            termination_reason="full_coverage",
        )
        assert result.inputs_generated == ({"x": 1}, {"x": 2})

    def test_run_result_is_frozen(self):
        result = RunConcolicResult(
            success=True,
            coverage_percent=0.0,
            executed_lines=frozenset(),
            paths_explored=0,
            inputs_generated=(),
            iterations=0,
            termination_reason="",
        )
        with pytest.raises((AttributeError, TypeError)):
            result.success = False  # type: ignore

    def test_from_exploration_converts_all_fields(self):
        exploration = _make_exploration_result(
            success=True,
            coverage_percent=80.0,
            executed_lines=frozenset({1, 2, 3}),
            paths_explored=2,
            iterations=4,
            termination_reason="max_iterations",
            elapsed_seconds=1.0,
        )
        inputs = [{"x": 1}, {"x": 2}]

        run_result = RunConcolicResult.from_exploration(exploration, inputs)

        assert run_result.success == exploration.success
        assert run_result.coverage_percent == exploration.coverage_percent
        assert run_result.executed_lines == exploration.executed_lines
        assert run_result.paths_explored == exploration.paths_explored
        assert run_result.inputs_generated == tuple(inputs)
        assert run_result.iterations == exploration.iterations
        assert run_result.termination_reason == exploration.termination_reason

    def test_from_exploration_with_empty_inputs(self):
        exploration = _make_exploration_result()
        run_result = RunConcolicResult.from_exploration(exploration, [])
        assert run_result.inputs_generated == ()
