"""Progress callback — fires after each iteration so an isolated runner
can checkpoint partial coverage over its pipe before a watchdog kill.

Without this hook, a child subprocess killed mid-exploration cannot
report any coverage gained after seed replay; everything up to that
point is lost. The callback lets the runner send a live snapshot of
(inputs_tried, covered_lines, iteration) after every completed
iteration so the parent can fall back to the latest checkpoint when
the child is force-killed.
"""

from __future__ import annotations

from typing import Any

from pyct.config.execution import ExecutionConfig
from pyct.engine.engine import Engine
from pyct.engine.state import ExplorationState


def _three_branch_target(x: int) -> int:
    """Target with three distinct branches — guarantees multiple iterations."""
    if x < 0:
        return -1
    if x == 0:
        return 0
    return 1


def test_progress_callback_fires_after_each_iteration() -> None:
    """Callback receives (engine, state) after every completed iteration.

    The key invariant: by the time the callback fires,
    ``state.iteration`` and ``state.inputs_tried`` reflect the just-
    completed iteration. The parent's checkpoint can rely on this
    consistency.
    """
    snapshots: list[dict[str, Any]] = []

    def on_progress(engine: Engine, state: ExplorationState) -> None:
        snapshots.append(
            {
                "iteration": state.iteration,
                "inputs_count": len(state.inputs_tried),
                "covered_count": len(state.covered_lines),
            }
        )

    config = ExecutionConfig(timeout_seconds=10.0, max_iterations=10)
    engine = Engine(config)
    engine.explore(
        _three_branch_target, {"x": 0}, progress_callback=on_progress
    )

    assert len(snapshots) >= 2, "expected multiple iterations"
    # inputs_tried is appended before state.iteration increments; both
    # reach the same value after the main-loop step, and the callback
    # fires once both are up-to-date.
    for snap in snapshots:
        assert snap["iteration"] == snap["inputs_count"], snap

    iterations = [snap["iteration"] for snap in snapshots]
    assert iterations == sorted(iterations), "iteration count must be monotonic"
    assert iterations[0] >= 1, "first callback fires after first iteration, not zero-th"


def test_progress_callback_absent_is_no_op() -> None:
    """Legacy callers that do not pass ``progress_callback`` see no behavior change."""
    config = ExecutionConfig(timeout_seconds=10.0, max_iterations=5)
    engine = Engine(config)
    result = engine.explore(_three_branch_target, {"x": 0})
    assert result.success is True
    assert result.iterations >= 1


def test_progress_callback_receives_growing_coverage() -> None:
    """Successive checkpoints show non-decreasing coverage.

    Mirrors what an isolated-runner parent expects: each checkpoint
    summarises at-least-as-much coverage as the previous one, so falling
    back to the latest snapshot never loses ground.
    """
    snapshots: list[int] = []

    def on_progress(_engine: Engine, state: ExplorationState) -> None:
        snapshots.append(len(state.covered_lines))

    config = ExecutionConfig(timeout_seconds=10.0, max_iterations=10)
    engine = Engine(config)
    engine.explore(
        _three_branch_target, {"x": 0}, progress_callback=on_progress
    )

    assert snapshots, "callback must fire at least once"
    for prev, nxt in zip(snapshots, snapshots[1:], strict=False):
        assert nxt >= prev, f"coverage regressed in snapshots: {snapshots}"
