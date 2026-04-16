"""PyCT — Python concolic testing with LLM-assisted discovery oracles."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pyct.config.execution import ExecutionConfig
from pyct.engine.engine import Engine
from pyct.engine.result import ExplorationResult, RunConcolicResult
from pyct.utils import logger as _logger  # noqa: F401  — registers smtlib2 log level

__version__ = "0.2.0"

__all__ = [
    "Engine",
    "ExecutionConfig",
    "ExplorationResult",
    "RunConcolicResult",
    "run_concolic",
]


def run_concolic(
    target: Callable,
    initial_args: dict[str, Any],
    *,
    config: ExecutionConfig | None = None,
    isolated: bool = True,
    seed_inputs: list[dict[str, Any]] | None = None,
    plugins: list | None = None,
) -> RunConcolicResult:
    """Run concolic exploration on ``target`` from ``initial_args``.

    This is the recommended entry point for general use. By default the
    target runs inside an isolated subprocess — a crash, ``sys.exit``
    call, or native hang in the target cannot take down the calling
    process, and the parent watchdog enforces a hard wall-clock limit.

    Pass ``isolated=False`` to run the engine directly in the caller's
    process. In-process mode is ~100 ms faster per call, supports
    in-function breakpoints, and accepts inline-defined targets that
    cannot be pickled — but loses the crash/hang safety net. Use it
    when you are debugging PyCT, profiling, or exploring a target you
    already trust to terminate cleanly.

    Args:
        target: The function to explore. Must be importable by module
            path when ``isolated=True``.
        initial_args: Dict mapping parameter name → concrete seed value.
        config: Optional :class:`ExecutionConfig`; defaults are used
            when omitted.
        isolated: When True (the default), run the engine inside a
            subprocess. When False, run in-process.
        seed_inputs: Pre-generated seed inputs for the engine's input
            queue. When provided, the engine skips on_seed_request
            dispatch. Used by the benchmark adapter for seed sharing
            between modes.
        plugins: Plugin instances to register on the engine before
            exploration. Must be pickleable when ``isolated=True``.

    Returns:
        A :class:`RunConcolicResult` describing the outcome.
    """
    exec_config = config if config is not None else ExecutionConfig()
    if isolated:
        from pyct.engine.isolated_runner import run_isolated

        return run_isolated(
            target,
            initial_args,
            exec_config,
            seed_inputs=seed_inputs,
            plugins=plugins,
        )
    return _run_in_process(
        target,
        initial_args,
        exec_config,
        seed_inputs=seed_inputs,
        plugins=plugins,
    )


def _run_in_process(
    target: Callable,
    initial_args: dict[str, Any],
    config: ExecutionConfig,
    *,
    seed_inputs: list[dict[str, Any]] | None = None,
    plugins: list | None = None,
) -> RunConcolicResult:
    """Run the engine directly in the current process."""
    engine = Engine(config)
    result = engine.explore(
        target,
        initial_args,
        seed_inputs=seed_inputs,
        plugins=plugins,
    )
    return RunConcolicResult.from_exploration(result, list(result.inputs_generated))
