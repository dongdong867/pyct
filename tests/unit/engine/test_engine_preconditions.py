"""Unit tests for engine precondition short-circuit telemetry and helper."""

from __future__ import annotations

from pyct.engine.engine import _build_result
from pyct.engine.result import ExplorationResult, RunConcolicResult
from pyct.engine.state import ExplorationState


def test_state_preconditions_violated_defaults_to_zero() -> None:
    state = ExplorationState()
    assert state.preconditions_violated == 0


def test_exploration_result_default_preconditions_violated_zero() -> None:
    fields_default = ExplorationResult.__dataclass_fields__["preconditions_violated"].default
    assert fields_default == 0


def test_build_result_threads_preconditions_violated_from_state() -> None:
    state = ExplorationState()
    state.preconditions_violated = 3
    state.termination_reason = "exhausted"
    result = _build_result(state, last_error=None)
    assert result.preconditions_violated == 3


def test_run_concolic_result_default_preconditions_violated_zero() -> None:
    fields_default = RunConcolicResult.__dataclass_fields__["preconditions_violated"].default
    assert fields_default == 0


def test_from_exploration_threads_preconditions_violated() -> None:
    exploration = ExplorationResult(
        success=True,
        coverage_percent=0.0,
        executed_lines=frozenset(),
        paths_explored=0,
        iterations=0,
        termination_reason="exhausted",
        elapsed_seconds=0.0,
        preconditions_violated=7,
    )
    public = RunConcolicResult.from_exploration(exploration, inputs=[])
    assert public.preconditions_violated == 7
