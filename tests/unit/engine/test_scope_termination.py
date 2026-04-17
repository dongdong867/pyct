"""Regression tests for coverage-scope termination.

Pins the fix for the thin-wrapper scope early-exit bug: when a target
function's body is a single line that delegates to deeper code, the
classical single-file coverage scope declares ``is_fully_covered`` the
moment the wrapper line runs — terminating exploration regardless of
how many branches remain in the helper. Supplying a wide scope that
tracks the helper file as well keeps the engine iterating until the
helper branches are covered (or the budget is exhausted).

The fixtures live in ``tests/unit/engine/_fixtures/`` so the modules
have stable ``__module__`` / ``__qualname__`` attributes that the
isolated-runner spawn path can re-import.
"""

from __future__ import annotations

from pyct import run_concolic
from pyct.config.execution import ExecutionConfig
from pyct.engine.coverage_scope import CoverageScope
from tests.unit.engine._fixtures import wrapper_helper, wrapper_target


class TestScopeEarlyExit:
    def test_narrow_scope_exits_after_first_seed(self):
        # Default scope (config.scope=None) narrows to wrapper_target.py
        # alone. One seed runs the single-line body, tracker reports full
        # coverage, engine terminates with reason=full_coverage.
        cfg = ExecutionConfig(timeout_seconds=10, solver_timeout=5, max_iterations=50)
        seeds = [{"s": ""}, {"s": "abcdef"}, {"s": "alpha"}, {"s": "gz"}]

        result = run_concolic(
            wrapper_target.classify,
            {"s": ""},
            config=cfg,
            isolated=False,
            seed_inputs=seeds,
        )

        assert result.success
        assert result.termination_reason == "full_coverage"
        assert result.iterations <= 2, (
            f"narrow scope should exit within 2 iterations once the wrapper "
            f"body is covered; got {result.iterations}"
        )

    def test_wide_scope_result_reports_cross_file_coverage(self):
        # Dual reporting: with wide scope, the engine should record lines
        # from BOTH wrapper_target.py AND wrapper_helper.py during
        # exploration — previously the tracer only saw target_file.
        wide = CoverageScope.for_paths(
            [wrapper_target.__file__, wrapper_helper.__file__],
            target_file=wrapper_target.__file__,
        )
        cfg = ExecutionConfig(
            timeout_seconds=15,
            solver_timeout=5,
            max_iterations=50,
            scope=wide,
        )
        seeds = [{"s": "abcdef"}, {"s": "alpha"}, {"s": "gz"}]

        result = run_concolic(
            wrapper_target.classify,
            {"s": ""},
            config=cfg,
            isolated=False,
            seed_inputs=seeds,
        )

        assert result.success
        # Wide-view totals populated from the tracker
        assert result.scope_total_lines > 0
        assert result.scope_executed_lines
        # Coverage includes lines from the helper file (not just target_file)
        files_covered = {path for path, _ in result.scope_executed_lines}
        assert wrapper_helper.__file__ in files_covered, (
            "widened tracer should record lines from helper file under wide scope"
        )
        # Scope percent is >0 and bounded
        assert 0 < result.scope_coverage_percent <= 100

    def test_wide_scope_iterates_through_seeds_and_reaches_helper(self):
        # Scope that covers both wrapper_target.py AND wrapper_helper.py.
        # The helper has four branches the wrapper delegates to; seed inputs
        # exercising those branches should all be consumed by the engine,
        # not skipped at iter=1.
        wide = CoverageScope.for_paths(
            [wrapper_target.__file__, wrapper_helper.__file__],
            target_file=wrapper_target.__file__,
        )
        cfg = ExecutionConfig(
            timeout_seconds=15,
            solver_timeout=5,
            max_iterations=50,
            scope=wide,
        )
        seeds = [
            {"s": ""},  # other
            {"s": "abcdef"},  # long
            {"s": "alpha"},  # starts_a
            {"s": "gz"},  # ends_z
        ]

        result = run_concolic(
            wrapper_target.classify,
            {"s": ""},
            config=cfg,
            isolated=False,
            seed_inputs=seeds,
        )

        assert result.success
        # Engine must iterate past iter=1 to exercise the helper branches.
        assert result.iterations >= 3, (
            f"wide scope should iterate through supplied seeds; got {result.iterations}"
        )
        # No full-coverage early exit — the helper has branches left uncovered
        # unless every seed runs, and even then coverage is partial.
        assert result.termination_reason != "full_coverage" or result.iterations >= 4
