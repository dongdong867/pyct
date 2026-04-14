"""Unit tests for EngineContext (read-only snapshot for plugins)."""

import inspect

import pytest

from pyct.config.execution import ExecutionConfig
from pyct.engine.plugin.context import EngineContext


def _sample_target(x: int) -> int:
    if x > 0:
        return 1
    return 0


def _make_context(
    iteration: int = 0,
    constraint_pool: tuple = (),
    covered_lines: frozenset[int] = frozenset(),
    total_lines: int = 0,
    inputs_tried: tuple = (),
    elapsed_seconds: float = 0.0,
) -> EngineContext:
    return EngineContext(
        iteration=iteration,
        constraint_pool=constraint_pool,
        covered_lines=covered_lines,
        total_lines=total_lines,
        inputs_tried=inputs_tried,
        target_function=_sample_target,
        target_signature=inspect.signature(_sample_target),
        config=ExecutionConfig(),
        elapsed_seconds=elapsed_seconds,
    )


class TestEngineContextConstruction:
    def test_context_with_all_fields(self):
        ctx = _make_context(
            iteration=5,
            constraint_pool=("constraint1", "constraint2"),
            covered_lines=frozenset({1, 2, 3}),
            total_lines=10,
            inputs_tried=({"x": 0}, {"x": 1}),
            elapsed_seconds=1.5,
        )
        assert ctx.iteration == 5
        assert ctx.constraint_pool == ("constraint1", "constraint2")
        assert ctx.covered_lines == frozenset({1, 2, 3})
        assert ctx.total_lines == 10
        assert ctx.inputs_tried == ({"x": 0}, {"x": 1})
        assert ctx.target_function is _sample_target
        assert ctx.elapsed_seconds == 1.5


class TestEngineContextImmutability:
    def test_context_is_frozen(self):
        ctx = _make_context()
        with pytest.raises((AttributeError, TypeError)):
            ctx.iteration = 10  # type: ignore

    def test_cannot_mutate_covered_lines(self):
        ctx = _make_context()
        with pytest.raises((AttributeError, TypeError)):
            ctx.covered_lines = frozenset({1})  # type: ignore


class TestEngineContextCoveragePercent:
    def test_coverage_percent_zero_when_no_total_lines(self):
        ctx = _make_context(total_lines=0)
        assert ctx.coverage_percent == 0.0

    def test_coverage_percent_zero_when_no_lines_covered(self):
        ctx = _make_context(total_lines=10, covered_lines=frozenset())
        assert ctx.coverage_percent == 0.0

    def test_coverage_percent_fifty_when_half_covered(self):
        ctx = _make_context(total_lines=10, covered_lines=frozenset({1, 2, 3, 4, 5}))
        assert ctx.coverage_percent == 50.0

    def test_coverage_percent_full_when_all_covered(self):
        ctx = _make_context(
            total_lines=5,
            covered_lines=frozenset({1, 2, 3, 4, 5}),
        )
        assert ctx.coverage_percent == 100.0
