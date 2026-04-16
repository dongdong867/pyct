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

import importlib
import multiprocessing as mp
import time
from collections.abc import Callable
from multiprocessing.connection import Connection, wait
from typing import Any

from pyct.config.execution import ExecutionConfig
from pyct.engine.engine import Engine
from pyct.engine.result import RunConcolicResult

_WATCHDOG_BUFFER_SECONDS = 5.0
"""How much longer the parent waits beyond the engine's timeout before killing.
Gives the engine a grace period to terminate cleanly from its own budget check."""


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
        args=(module_name, qualname, initial_args, config, child_conn,
              seed_inputs, plugins),
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
    """Child-process entry point: import target, run engine, send result."""
    try:
        target = _import_target(module_name, qualname)
        engine = Engine(config)
        exploration = engine.explore(
            target, initial_args,
            seed_inputs=seed_inputs, plugins=plugins,
        )
        token_stats = _extract_plugin_tokens(plugins or [])
        result = RunConcolicResult.from_exploration(
            exploration,
            list(exploration.inputs_generated),
            token_stats=token_stats,
        )
    except Exception as e:
        result = _wrapper_failure(f"{type(e).__name__}: {e}")

    try:
        pipe.send(result)
    finally:
        pipe.close()


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
    """Block until the child sends a result, dies, or the watchdog fires."""
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            proc.kill()
            return _wrapper_failure(f"child exceeded wall-clock timeout of {timeout:.1f}s")

        ready = wait([conn, proc.sentinel], timeout=remaining)
        if not ready:
            continue
        if conn in ready:
            try:
                return conn.recv()
            except EOFError:
                return _wrapper_failure("child closed pipe without sending result")
        if proc.sentinel in ready:
            return _wrapper_failure(f"child exited unexpectedly (exit code {proc.exitcode})")


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
