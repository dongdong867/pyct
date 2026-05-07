"""Pipe-checkpoint protocol and watchdog fallback for isolated runs.

Before this fix, a watchdog kill returned ``RunConcolicResult`` with
empty ``executed_lines`` and empty ``inputs_generated``, dropping any
coverage the concolic loop had gained after seed replay. These tests
pin the replacement behaviour: the child emits ``("progress", result)``
checkpoints after every iteration and a single ``("final", result)``
terminator, and the parent's ``_wait_for_result`` returns the latest
checkpoint on watchdog kill instead of a fabricated empty failure.
"""

from __future__ import annotations

import multiprocessing as mp
import time
from typing import Any

from pyct.engine.isolated_runner import _wait_for_result
from pyct.engine.result import RunConcolicResult


def _make_result(*, iterations: int, termination_reason: str = "partial") -> RunConcolicResult:
    return RunConcolicResult(
        success=False,
        coverage_percent=50.0 * iterations,
        executed_lines=frozenset(range(1, iterations + 2)),
        paths_explored=iterations,
        inputs_generated=tuple({"x": i} for i in range(iterations)),
        iterations=iterations,
        termination_reason=termination_reason,
    )


def _child_send_progress_then_sleep(pipe: Any) -> None:
    """Send two checkpoints, then hang past the parent's timeout."""
    pipe.send(("progress", _make_result(iterations=1)))
    time.sleep(0.05)
    pipe.send(("progress", _make_result(iterations=2)))
    time.sleep(100)


def _child_send_progress_then_final(pipe: Any) -> None:
    """Send one checkpoint, then a final result, then exit cleanly."""
    pipe.send(("progress", _make_result(iterations=1)))
    time.sleep(0.02)
    pipe.send(("final", _make_result(iterations=7, termination_reason="full_coverage")))


def _child_exit_without_sending(pipe: Any) -> None:
    """Close the pipe immediately without any message."""
    pipe.close()


def _run_child_and_wait(
    target: Any,
    *,
    timeout: float,
) -> RunConcolicResult:
    ctx = mp.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=target, args=(child_conn,))
    proc.start()
    child_conn.close()
    try:
        return _wait_for_result(parent_conn, proc, timeout=timeout)
    finally:
        if proc.is_alive():
            proc.kill()
        proc.join(timeout=2)


def test_wait_for_result_returns_latest_checkpoint_on_watchdog() -> None:
    """Child sends two progress checkpoints then hangs; parent timeout
    returns the *latest* checkpoint, not an empty wrapper failure."""
    result = _run_child_and_wait(_child_send_progress_then_sleep, timeout=1.0)

    assert result.iterations == 2, "latest checkpoint should win"
    assert result.inputs_generated == ({"x": 0}, {"x": 1})
    assert result.executed_lines == frozenset({1, 2, 3})
    # Termination carries over from the checkpoint so the parent can
    # distinguish partial-checkpoint cases from clean completion.
    assert result.termination_reason == "partial"


def test_wait_for_result_prefers_final_over_checkpoint() -> None:
    """When both a checkpoint and a final are sent, parent returns the final."""
    result = _run_child_and_wait(_child_send_progress_then_final, timeout=3.0)

    assert result.iterations == 7
    assert result.termination_reason == "full_coverage"


def test_wait_for_result_falls_back_to_wrapper_failure_without_messages() -> None:
    """No checkpoint ever received → legacy behaviour: empty wrapper failure."""
    result = _run_child_and_wait(_child_exit_without_sending, timeout=2.0)

    assert result.success is False
    assert result.iterations == 0
    assert result.executed_lines == frozenset()
    assert result.inputs_generated == ()
    assert result.error is not None


def _child_iter_start_then_sleep(pipe: Any) -> None:
    """Send iter_start without ever following with progress; then hang.

    Models a watchdog kill mid-iteration: the parent must reconstruct
    the in-flight iter as a TIMEOUT record from the iter_start payload.
    """
    pipe.send(("progress", _make_result(iterations=1)))  # one completed iter
    pipe.send(
        (
            "iter_start",
            {"idx": 1, "args": {"x": 99}, "provenance": "solver"},
        )
    )
    time.sleep(100)


def _child_iter_start_then_progress(pipe: Any) -> None:
    """iter_start followed by progress that covers it — tombstone NOT inserted."""
    pipe.send(("progress", _make_result(iterations=1)))
    pipe.send(("iter_start", {"idx": 1, "args": {"x": 5}, "provenance": "solver"}))
    pipe.send(("progress", _make_result(iterations=2)))
    time.sleep(100)


def _child_two_starts_only_first_progressed(pipe: Any) -> None:
    """Two iter_starts; only the first ends in progress. Tombstone for second."""
    pipe.send(("iter_start", {"idx": 0, "args": {"x": 1}, "provenance": "seed"}))
    pipe.send(("progress", _make_result(iterations=1)))
    pipe.send(
        (
            "iter_start",
            {"idx": 1, "args": {"x": 2}, "provenance": "plugin_seed"},
        )
    )
    time.sleep(100)


def _child_iter_start_no_checkpoint_then_sleep(pipe: Any) -> None:
    """iter_start before any progress arrives. Tombstone is the only record."""
    pipe.send(("iter_start", {"idx": 0, "args": {"x": 7}, "provenance": "seed"}))
    time.sleep(100)


class TestTombstoneRecovery:
    """Watchdog kill mid-iteration → parent reconstructs TIMEOUT record."""

    def test_pending_iter_start_becomes_timeout_record(self) -> None:
        from pyct.engine.types import Outcome, Provenance

        result = _run_child_and_wait(_child_iter_start_then_sleep, timeout=1.0)

        # Latest checkpoint had 1 record; tombstone adds the second.
        assert result.iterations == 2
        assert len(result.inputs_generated) == 2
        tombstone = result.inputs_generated[-1]
        assert tombstone.outcome is Outcome.TIMEOUT
        assert tombstone.args == {"x": 99}
        assert tombstone.provenance is Provenance.SOLVER
        assert tombstone.error is not None
        assert tombstone.error.startswith("timeout:")
        assert result.termination_reason == "timeout"

    def test_progress_after_iter_start_clears_pending(self) -> None:
        """When progress arrives covering the iter_start, no tombstone is added."""
        result = _run_child_and_wait(_child_iter_start_then_progress, timeout=1.0)

        # Latest checkpoint had 2 records; iter_start was covered → no
        # tombstone augmentation, so termination_reason stays "partial"
        # (the checkpoint's value) rather than being overwritten with
        # "timeout" by the pending-iter-start finalizer.
        assert result.iterations == 2
        assert len(result.inputs_generated) == 2
        assert result.termination_reason != "timeout"

    def test_only_unmatched_iter_start_becomes_tombstone(self) -> None:
        from pyct.engine.types import Outcome, Provenance

        result = _run_child_and_wait(_child_two_starts_only_first_progressed, timeout=1.0)

        # First iter_start was covered by the progress message; second wasn't.
        assert result.iterations == 2
        assert len(result.inputs_generated) == 2
        tombstone = result.inputs_generated[-1]
        assert tombstone.outcome is Outcome.TIMEOUT
        assert tombstone.args == {"x": 2}
        assert tombstone.provenance is Provenance.PLUGIN_SEED

    def test_tombstone_with_no_prior_checkpoint(self) -> None:
        """iter_start before any progress → tombstone is the only record."""
        from pyct.engine.types import Outcome, Provenance

        result = _run_child_and_wait(_child_iter_start_no_checkpoint_then_sleep, timeout=1.0)

        assert len(result.inputs_generated) == 1
        tombstone = result.inputs_generated[0]
        assert tombstone.outcome is Outcome.TIMEOUT
        assert tombstone.args == {"x": 7}
        assert tombstone.provenance is Provenance.SEED


def _slow_plugin_target(x: int, y: int, z: int) -> int:
    """Multi-branch target with a hard-to-solve corner so full coverage
    doesn't come in one iteration; plateau fires instead and the slow
    plugin below hangs during dispatch."""
    if x > 100 and y > 100 and z > 100:
        return 1
    if x < -100 and y < -100 and z < -100:
        return -1
    return 0


class _SlowPlateauPlugin:
    """Burns wall-clock in ``on_coverage_plateau`` so the watchdog fires
    mid-dispatch. Mirrors the real-world mode-C failure where chained LLM
    calls overrun the ``config.timeout_seconds`` + buffer budget."""

    name = "slow_plateau"
    priority = 100

    def on_coverage_plateau(self, ctx: Any) -> list[dict[str, Any]]:
        time.sleep(60)  # hangs long enough to force a watchdog kill
        return []


def test_isolated_run_preserves_concolic_coverage_on_watchdog_kill(monkeypatch: Any) -> None:
    """Full pipeline: child runs real engine, plugin hangs during plateau,
    watchdog kills the subprocess, parent recovers the last checkpoint.

    Before the fix, ``result.executed_lines`` and ``result.inputs_generated``
    were empty after a watchdog kill — this test locks in that concolic
    coverage gathered before the hang is preserved through the kill.
    """
    from pyct.config.execution import ExecutionConfig
    from pyct.engine.isolated_runner import run_isolated

    monkeypatch.setattr("pyct.engine.isolated_runner._WATCHDOG_BUFFER_SECONDS", 1.0)

    config = ExecutionConfig(
        timeout_seconds=2.0,
        max_iterations=10,
        plateau_threshold=1,
        solver_timeout=5,
    )

    result = run_isolated(
        _slow_plugin_target,
        {"x": 0, "y": 0, "z": 0},
        config,
        plugins=[_SlowPlateauPlugin()],
    )

    # Engine had time to run at least one concolic iteration before the
    # plugin hung during plateau dispatch and the watchdog killed the child.
    assert result.iterations >= 1, "expected at least one iteration checkpointed"
    assert result.inputs_generated, "expected inputs from checkpoint, not empty"
    assert result.executed_lines, "expected some covered lines, not empty"
    assert result.termination_reason == "partial_checkpoint"
