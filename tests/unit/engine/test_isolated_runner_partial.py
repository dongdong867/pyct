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

    monkeypatch.setattr(
        "pyct.engine.isolated_runner._WATCHDOG_BUFFER_SECONDS", 1.0
    )

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
