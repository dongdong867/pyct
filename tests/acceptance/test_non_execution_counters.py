"""Acceptance tests: non-execution counters.

The engine emits three diagnostic counters that record events which did
*not* produce an executed input:

- ``gen_unsat``: solver returned UNSAT for a path constraint (provably
  unreachable, no input possible).
- ``gen_unknown``: solver returned UNKNOWN or ERROR (gave up).
  Counted raw — every UNKNOWN bumps the counter, regardless of whether
  a plugin's ``on_constraint_unknown`` resolver later produced an
  alternate input.
- ``harness_error``: ``wrap_arguments`` raised. The iteration ran no
  target code; the engine logged a record carrying the wrap error and
  bumped this counter.
"""

from __future__ import annotations

from typing import Any

from pyct.config.execution import ExecutionConfig
from pyct.engine import engine as engine_module
from pyct.engine.engine import Engine
from pyct.solver.executor import SolverStatus


def _two_branch(x: int) -> int:
    """One reachable branch — generates one constraint per iteration."""
    if x > 10:
        return 1
    return 0


def _passthrough(x: int) -> int:
    """No branches — fewest moving parts for harness-error tests."""
    return x


class _UnknownResolver:
    """Plugin that resolves on_constraint_unknown with a canned arg."""

    name = "unknown_resolver"
    priority = 100

    def __init__(self, resolution: dict[str, Any]) -> None:
        self._resolution = resolution
        self.calls = 0

    def on_constraint_unknown(self, ctx: Any, constraint: Any) -> dict[str, Any] | None:
        self.calls += 1
        return dict(self._resolution)


def _patch_solve(monkeypatch, engine: Engine, status: SolverStatus) -> None:
    """Make ``engine._solve`` always return ``(None, status)``.

    Bypasses the actual cvc5 subprocess so a test can deterministically
    drive the engine into UNSAT or UNKNOWN paths regardless of what the
    real solver would produce for the target's constraints.
    """

    def fake_solve(constraint, var_to_types, base_args):  # noqa: ARG001
        return None, status

    monkeypatch.setattr(engine, "_solve", fake_solve)


class TestCountersDefaultZero:
    """Clean run — no UNSAT, no UNKNOWN, no harness error → all zero."""

    def test_clean_run_has_all_counters_zero(self):
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        result = engine.explore(_two_branch, {"x": 0})

        assert result.gen_unsat == 0
        assert result.gen_unknown == 0
        assert result.harness_error == 0


class TestUnsatCounter:
    """Every UNSAT solver outcome bumps ``gen_unsat``."""

    def test_unsat_outcomes_increment_counter(self, monkeypatch):
        """
        Given an engine whose solver always returns UNSAT
          And a target whose seed produces at least one path constraint
        When exploration drains the constraint pool
        Then gen_unsat equals the number of UNSAT solver calls
          And no records are added beyond the seed (UNSAT yields no input)
        """
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        _patch_solve(monkeypatch, engine, SolverStatus.UNSAT)

        result = engine.explore(_two_branch, {"x": 0})

        # The seed runs once and registers at least one constraint;
        # every subsequent _solve call returns UNSAT and bumps the counter.
        assert result.gen_unsat >= 1
        assert result.gen_unknown == 0
        assert result.harness_error == 0
        # Only the seed produced a record — UNSAT solves yield no inputs.
        assert len(result.inputs_generated) == 1


class TestUnknownCounter:
    """Every UNKNOWN/ERROR solver outcome bumps ``gen_unknown``."""

    def test_unresolved_unknown_increments_counter(self, monkeypatch):
        """
        Given an engine whose solver always returns UNKNOWN
          And no plugin registered to resolve unknowns
        When the engine processes the constraint pool
        Then gen_unknown is positive
          And gen_unsat stays zero
        """
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        _patch_solve(monkeypatch, engine, SolverStatus.UNKNOWN)

        result = engine.explore(_two_branch, {"x": 0})

        assert result.gen_unknown >= 1
        assert result.gen_unsat == 0

    def test_resolved_unknown_still_increments_counter(self, monkeypatch):
        """
        Given an engine whose solver always returns UNKNOWN
          And a plugin that resolves on_constraint_unknown with a canned arg
        When the resolver supplies an alternate input
        Then gen_unknown still bumps for the raw UNKNOWN solver outcome
          (raw counting — resolution is orthogonal)
          And the resolved input appears in inputs_generated
        """
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        engine.register(_UnknownResolver(resolution={"x": 999}))
        _patch_solve(monkeypatch, engine, SolverStatus.UNKNOWN)

        result = engine.explore(_two_branch, {"x": 0})

        assert result.gen_unknown >= 1
        # Resolved input (x=999) ran as an iteration with PLUGIN_UNKNOWN
        # provenance — provenance test family covers tagging; here we only
        # verify the resolution path doesn't suppress the counter.
        resolved_args = [r.args for r in result.inputs_generated]
        assert {"x": 999} in resolved_args

    def test_solver_error_status_also_increments_unknown(self, monkeypatch):
        """
        Given an engine whose solver returns ERROR (solver crashed)
        When the engine processes the constraint pool
        Then gen_unknown bumps (ERROR is bucketed with UNKNOWN — both
            mean "no model produced, may be retryable")
        """
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        _patch_solve(monkeypatch, engine, SolverStatus.ERROR)

        result = engine.explore(_two_branch, {"x": 0})

        assert result.gen_unknown >= 1
        assert result.gen_unsat == 0


class TestHarnessErrorCounter:
    """``wrap_arguments`` failures bump ``harness_error``."""

    def test_wrap_failure_increments_counter(self, monkeypatch):
        """
        Given a wrap_arguments stub that raises on a specific seed
        When the engine attempts that seed
        Then harness_error increments by one for that attempt
          And exploration continues for other seeds
        """
        original = engine_module.wrap_arguments
        crash_args = {"x": 666}

        def flaky_wrap(args, engine):
            if args == crash_args:
                raise AttributeError("simulated wrap failure")
            return original(args, engine)

        monkeypatch.setattr(engine_module, "wrap_arguments", flaky_wrap)

        engine = Engine(ExecutionConfig(max_iterations=10, timeout_seconds=5.0))
        result = engine.explore(
            _two_branch,
            {"x": -5},
            seed_inputs=[crash_args, {"x": 7}],
        )

        assert result.harness_error == 1
        # Other seeds still ran — error containment preserved.
        tried = {tuple(sorted(r.args.items())) for r in result.inputs_generated}
        assert (("x", 7),) in tried

    def test_multiple_wrap_failures_accumulate(self, monkeypatch):
        """
        Given a wrap stub that raises on every seed
        When exploration runs through several seeds
        Then harness_error equals the number of failed wraps
        """
        crash_seeds = [{"x": 1}, {"x": 2}, {"x": 3}]

        def always_crash(args, engine):  # noqa: ARG001
            raise AttributeError("always fails")

        monkeypatch.setattr(engine_module, "wrap_arguments", always_crash)

        engine = Engine(ExecutionConfig(max_iterations=10, timeout_seconds=5.0))
        result = engine.explore(
            _passthrough,
            {"x": 0},
            seed_inputs=crash_seeds,
        )

        # initial seed (x=0) + 3 crash seeds — every wrap fails
        assert result.harness_error == 4


class TestCountersOnRunConcolicResult:
    """Counters surface on the public RunConcolicResult shape too."""

    def test_run_concolic_result_carries_counters(self, monkeypatch):
        from pyct.engine.result import RunConcolicResult

        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        _patch_solve(monkeypatch, engine, SolverStatus.UNSAT)
        exploration = engine.explore(_two_branch, {"x": 0})

        run_result = RunConcolicResult.from_exploration(
            exploration, list(exploration.inputs_generated)
        )

        assert run_result.gen_unsat == exploration.gen_unsat
        assert run_result.gen_unknown == exploration.gen_unknown
        assert run_result.harness_error == exploration.harness_error
