"""Unit tests for engine precondition short-circuit telemetry and helper."""

from __future__ import annotations

from pyct.engine.state import ExplorationState


def test_state_preconditions_violated_defaults_to_zero() -> None:
    state = ExplorationState()
    assert state.preconditions_violated == 0
