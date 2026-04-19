"""Subprocess wrapper that runs ``Engine.explore`` in a sandboxed child.

The public ``run_concolic`` function delegates here when ``isolated=True``.
The child process imports the target by module path + qualified name,
runs the entire concolic loop in-process inside that child, and returns
a ``RunConcolicResult`` through a pipe. The parent enforces a
wall-clock watchdog: if the child hangs in native code or exceeds the
budget, the parent force-kills it and surfaces a failure result.

Only one fork happens per ``run_concolic`` call — not per iteration —
so the overhead is ~100 ms regardless of how many iterations the loop
runs. Crashes in the target (SIGSEGV, OOM, ``sys.exit``, native hangs)
are contained to the child.
"""

from __future__ import annotations

import contextlib
import importlib
import multiprocessing as mp
import time
from collections.abc import Callable
from multiprocessing.connection import Connection, wait
from typing import Any

from pyct.config.execution import ExecutionConfig
from pyct.engine.engine import Engine
from pyct.engine.result import RunConcolicResult

_WATCHDOG_BUFFER_SECONDS = 20.0
"""How much longer the parent waits beyond the engine's timeout before killing.

Must exceed solver_timeout (default 15s) so the engine can finish its
current solver call, terminate from the budget check, build the result,
and send it through the pipe. With 5s buffer, the parent killed the child
mid-solver-call and lost partial coverage. 20s covers one solver_timeout
(15s) + cleanup (5s)."""


def run_isolated(
    target: Callable,
    initial_args: dict[str, Any],
    config: ExecutionConfig,
    *,
    seed_inputs: list[dict[str, Any]] | None = None,
    plugins: list | None = None,
) -> RunConcolicResult:
    """Run the engine in a subprocess, returning the serialized result."""
    module_name, qualname = _describe_target(target)

    ctx = mp.get_context("spawn")
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(
        target=_child_entry,
        args=(module_name, qualname, initial_args, config, child_conn, seed_inputs, plugins),
    )
    proc.start()
    child_conn.close()

    try:
        result = _wait_for_result(
            parent_conn,
            proc,
            timeout=config.timeout_seconds + _WATCHDOG_BUFFER_SECONDS,
        )
    finally:
        _reap_child(proc)
    return result


def _describe_target(target: Callable) -> tuple[str, str]:
    """Return ``(module_name, qualname)`` for a target importable in a child.

    Inline functions (``def foo`` inside another function) have
    ``<locals>`` in their qualname and cannot be re-imported from a
    fresh interpreter. We raise a clear error pointing the caller at
    the ``isolated=False`` escape hatch.
    """
    module_name = getattr(target, "__module__", None)
    qualname = getattr(target, "__qualname__", None)
    if module_name is None or qualname is None:
        raise TypeError(
            f"Cannot isolate target {target!r} — missing __module__ or __qualname__. "
            "Define it at module level, or pass isolated=False."
        )
    if "<locals>" in qualname:
        raise TypeError(
            f"Cannot isolate target {target!r} — it is defined inside a function. "
            "Define it at module level, or pass isolated=False."
        )
    return module_name, qualname


def _child_entry(
    module_name: str,
    qualname: str,
    initial_args: dict[str, Any],
    config: ExecutionConfig,
    pipe: Connection,
    seed_inputs: list[dict[str, Any]] | None = None,
    plugins: list | None = None,
) -> None:
    """Child-process entry point: import target, run engine, send result.

    Pipe protocol: ``(kind, RunConcolicResult)`` tuples, where ``kind``
    is ``"progress"`` for every completed iteration and ``"final"`` for
    the terminal result. Earlier revisions sent a bare result on the
    pipe; the tag lets the parent fall back to the latest ``"progress"``
    payload when the watchdog kills the child before ``"final"`` lands.
    """
    import io
    import sys

    sys.stdout = io.StringIO()
    sys.stderr = io.StringIO()

    plugins_list = plugins or []

    def emit_progress(engine: Engine, state: Any) -> None:
        partial = _partial_result_from_state(engine, state, plugins_list)
        # Parent may have closed the pipe already (e.g. after killing us);
        # dropping the send keeps the engine loop alive so a clean ``final``
        # can still be attempted if we somehow survive.
        with contextlib.suppress(BrokenPipeError, EOFError, OSError):
            pipe.send(("progress", partial))

    try:
        target = _import_target(module_name, qualname)
        engine = Engine(config)
        exploration = engine.explore(
            target,
            initial_args,
            seed_inputs=seed_inputs,
            plugins=plugins,
            progress_callback=emit_progress,
        )
        token_stats = _extract_plugin_tokens(plugins_list)
        result = RunConcolicResult.from_exploration(
            exploration,
            list(exploration.inputs_generated),
            token_stats=token_stats,
        )
    except Exception as e:
        result = _wrapper_failure(f"{type(e).__name__}: {e}")

    try:
        pipe.send(("final", result))
    finally:
        pipe.close()


def _partial_result_from_state(
    engine: Engine,
    state: Any,
    plugins: list,
) -> RunConcolicResult:
    """Snapshot engine + state into a RunConcolicResult for pipe delivery.

    Mirrors the shape ``_pyct_result_to_runner`` consumes on the parent
    side so the benchmark's coverage-from-inputs rerun path works
    identically whether we got a ``final`` or fell back to a ``progress``
    checkpoint. Success is marked False on a partial so callers can
    distinguish partial-checkpoint cases from clean completion.
    """
    tracker = engine.coverage_tracker
    narrow_lines = frozenset(state.observed_lines)
    narrow_total = state.total_lines or 0
    narrow_percent = (100.0 * len(narrow_lines) / narrow_total) if narrow_total else 0.0

    scope_lines: frozenset[tuple[str, int]] = frozenset()
    scope_total = 0
    scope_percent = 0.0
    if tracker is not None:
        scope_lines = frozenset(
            (path, line)
            for path, lines in tracker.observed_by_file.items()
            for line in lines
        )
        scope_total = tracker.total_lines
        scope_percent = tracker.coverage_percent

    return RunConcolicResult(
        success=False,
        coverage_percent=narrow_percent,
        executed_lines=narrow_lines,
        paths_explored=len(state.inputs_tried),
        inputs_generated=tuple(state.inputs_tried),
        iterations=state.iteration,
        termination_reason="partial_checkpoint",
        error=None,
        token_stats=_extract_plugin_tokens(plugins),
        scope_coverage_percent=scope_percent,
        scope_executed_lines=scope_lines,
        scope_total_lines=scope_total,
    )


def _import_target(module_name: str, qualname: str) -> Callable:
    """Re-import a target by module path and dotted qualified name."""
    module = importlib.import_module(module_name)
    obj: Any = module
    for attr in qualname.split("."):
        obj = getattr(obj, attr)
    if not callable(obj):
        raise TypeError(f"resolved target {qualname} in {module_name} is not callable")
    return obj


def _wait_for_result(
    conn: Connection,
    proc: mp.process.BaseProcess,
    timeout: float,
) -> RunConcolicResult:
    """Block until the child sends ``final``, dies, or the watchdog fires.

    Drains ``("progress", result)`` checkpoints into ``last_checkpoint``
    until either a ``("final", result)`` arrives (preferred), the pipe
    closes / the child exits, or the deadline passes. On watchdog kill
    or unexpected exit, the latest checkpoint is returned so the parent
    still sees the concolic-iteration coverage gathered before the kill;
    only when no checkpoint was ever received do we fall back to the
    legacy empty-coverage wrapper failure.
    """
    deadline = time.monotonic() + timeout
    last_checkpoint: RunConcolicResult | None = None

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            proc.kill()
            return _checkpoint_or_failure(
                last_checkpoint,
                f"child exceeded wall-clock timeout of {timeout:.1f}s",
            )

        ready = wait([conn, proc.sentinel], timeout=remaining)
        if not ready:
            continue
        if conn in ready:
            try:
                message = conn.recv()
            except EOFError:
                return _checkpoint_or_failure(
                    last_checkpoint, "child closed pipe without sending result"
                )
            kind, payload = _parse_pipe_message(message)
            if kind == "final":
                return payload
            last_checkpoint = payload  # kind == "progress"
            continue
        if proc.sentinel in ready:
            return _checkpoint_or_failure(
                last_checkpoint,
                f"child exited unexpectedly (exit code {proc.exitcode})",
            )


def _parse_pipe_message(
    message: Any,
) -> tuple[str, RunConcolicResult]:
    """Unpack a ``(kind, payload)`` tuple; treat legacy bare payloads as final.

    The bare-RunConcolicResult shape is what child processes sent before
    the checkpoint protocol landed; accepting it keeps mixed-version
    testing clean while the codebase converges.
    """
    if isinstance(message, tuple) and len(message) == 2:
        kind, payload = message
        if kind in ("progress", "final") and isinstance(payload, RunConcolicResult):
            return kind, payload
    if isinstance(message, RunConcolicResult):
        return "final", message
    raise TypeError(f"unexpected pipe message shape: {type(message).__name__}")


def _checkpoint_or_failure(
    checkpoint: RunConcolicResult | None,
    failure_message: str,
) -> RunConcolicResult:
    """Return the latest checkpoint if any, else a fresh wrapper failure.

    The checkpoint path preserves concolic-iteration coverage that would
    otherwise be dropped on watchdog kill; without a checkpoint we fall
    back to the original empty-coverage behaviour so tests that rely on
    the legacy ``success=False`` signature still pass.
    """
    if checkpoint is not None:
        return checkpoint
    return _wrapper_failure(failure_message)


def _reap_child(proc: mp.process.BaseProcess) -> None:
    """Join the child; force-kill if it hasn't exited."""
    proc.join(timeout=2)
    if proc.is_alive():
        proc.kill()
        proc.join(timeout=1)


def _extract_plugin_tokens(plugins: list) -> dict[str, int] | None:
    """Extract accumulated token usage from plugins after exploration."""
    for plugin in plugins:
        client = getattr(plugin, "_client", None)
        if client is None:
            continue
        get_stats = getattr(client, "get_stats", None)
        if get_stats is None:
            continue
        stats = get_stats()
        inp = stats.get("input_tokens", 0)
        out = stats.get("output_tokens", 0)
        if inp or out:
            return {"input_tokens": inp, "output_tokens": out}
    return None


def _wrapper_failure(message: str) -> RunConcolicResult:
    """Build a failure result when the isolation wrapper itself couldn't run."""
    return RunConcolicResult(
        success=False,
        coverage_percent=0.0,
        executed_lines=frozenset(),
        paths_explored=0,
        inputs_generated=(),
        iterations=0,
        termination_reason="error",
        error=message,
    )
