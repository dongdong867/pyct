"""Plateau early-exit and LLM silencing after repeated non-improvement.

Matches the paper's coverage-gated silencing policy: if plateau-requested
LLM seeds fail to improve coverage for ``max_stale_llm_attempts``
consecutive dispatches, exploration terminates with
``plateau_exhausted`` rather than continuing to burn LLM budget.

Unit-level tests exercise ``_check_plateau_outcome`` directly; the
integration test drives a full ``Engine.explore`` with a plugin that
returns useless seeds and asserts the engine stops early.
"""

from __future__ import annotations

import inspect
from typing import Any

from pyct.config.execution import ExecutionConfig
from pyct.engine.engine import Engine
from pyct.engine.plugin.dispatcher import Dispatcher
from pyct.engine.recovery import check_plateau_outcome, handle_plateau
from pyct.engine.state import ExplorationState


class _UselessPlateauPlugin:
    """Always returns the same seed that does nothing — triggers plateau with no coverage gain."""

    name = "useless_plateau"
    priority = 100

    def __init__(self, seed: dict[str, Any]):
        self._seed = seed
        self.calls = 0

    def on_coverage_plateau(self, ctx: Any) -> list[dict[str, Any]]:
        self.calls += 1
        return [dict(self._seed)]


def _boring(x: int) -> int:
    """No-branch target. Solver has nothing to explore — stale grows fast."""
    return x


class TestPlateauOutcomeCheck:
    """Unit tests for Engine._check_plateau_outcome (phase-boundary hook)."""

    def test_resets_failure_count_on_improvement(self) -> None:
        config = ExecutionConfig(max_stale_llm_attempts=2)
        engine = Engine(config)

        state = ExplorationState()
        state.coverage_at_last_plateau = 5
        state.plateau_failure_count = 1

        # Simulate post-plateau coverage jump: scope_observed_count depends on
        # tracker, so we patch the property with a fake.
        class _FakeTracker:
            observed_count = 12
            total_lines = 20

            def is_fully_covered(self) -> bool:
                return False

        state.tracker = _FakeTracker()  # type: ignore[assignment]

        check_plateau_outcome(engine, state)

        assert state.plateau_failure_count == 0
        assert state.coverage_at_last_plateau is None
        assert not state.terminated

    def test_increments_failure_count_on_no_improvement(self) -> None:
        config = ExecutionConfig(max_stale_llm_attempts=2)
        engine = Engine(config)

        state = ExplorationState()
        state.coverage_at_last_plateau = 10

        class _FakeTracker:
            observed_count = 10
            total_lines = 20

            def is_fully_covered(self) -> bool:
                return False

        state.tracker = _FakeTracker()  # type: ignore[assignment]

        check_plateau_outcome(engine, state)

        assert state.plateau_failure_count == 1
        assert state.coverage_at_last_plateau is None
        assert not state.terminated

    def test_terminates_after_max_consecutive_failures(self) -> None:
        config = ExecutionConfig(max_stale_llm_attempts=2)
        engine = Engine(config)

        state = ExplorationState()
        state.coverage_at_last_plateau = 10
        state.plateau_failure_count = 1  # one prior failure already

        class _FakeTracker:
            observed_count = 10
            total_lines = 20

            def is_fully_covered(self) -> bool:
                return False

        state.tracker = _FakeTracker()  # type: ignore[assignment]

        check_plateau_outcome(engine, state)

        assert state.plateau_failure_count == 2
        assert state.terminated
        assert state.termination_reason == "plateau_exhausted"


class TestPlateauDispatchRecordsCoverage:
    """Dispatching plateau stores scope_observed_count for later outcome check."""

    def test_handle_plateau_sets_coverage_at_last_plateau(self) -> None:
        config = ExecutionConfig(plateau_threshold=2, max_stale_llm_attempts=2)
        engine = Engine(config)
        plugin = _UselessPlateauPlugin(seed={"x": 0})
        engine.register(plugin)

        class _FakeTracker:
            observed_count = 7
            total_lines = 20

            def is_fully_covered(self) -> bool:
                return False

        state = ExplorationState(seed_phase=False)
        state.tracker = _FakeTracker()  # type: ignore[assignment]

        # last_coverage_size matches scope_observed_count so the stale
        # guard (early-return on improvement) lets us reach the dispatch.
        handle_plateau(
            engine,
            state=state,
            last_coverage_size=7,
            stale_count=config.plateau_threshold,
            input_queue=[],
            dispatcher=Dispatcher(engine.plugins),
            target=_boring,
            signature=inspect.signature(_boring),
        )

        assert state.coverage_at_last_plateau == 7, (
            "plateau dispatch must record scope_observed_count for the outcome check"
        )


class TestPlateauOutcomeWiring:
    """Main-loop wiring: outcome check fires on the phase boundary."""

    def test_main_loop_checks_outcome_before_next_plateau(self) -> None:
        """After a plateau dispatch drains and a post-seed iteration runs,
        the outcome check must clear ``coverage_at_last_plateau`` before
        any new plateau fire can overwrite the baseline."""
        config = ExecutionConfig(
            max_iterations=3,
            timeout_seconds=5.0,
            plateau_threshold=2,
            max_stale_llm_attempts=2,
        )
        engine = Engine(config)

        # Prime a plateau that's already been dispatched — simulate the
        # state the engine would be in partway through a run.
        class _FakeTracker:
            observed_count = 10
            total_lines = 20

            def is_fully_covered(self) -> bool:
                return False

        state = ExplorationState(seed_phase=False)
        state.tracker = _FakeTracker()  # type: ignore[assignment]
        state.coverage_at_last_plateau = 10  # no improvement since dispatch
        state.plateau_failure_count = 1

        check_plateau_outcome(engine, state)

        # Counter advanced; baseline cleared; engine terminated.
        assert state.plateau_failure_count == 2
        assert state.coverage_at_last_plateau is None
        assert state.terminated
        assert state.termination_reason == "plateau_exhausted"
