"""LLM-driven recovery: plateau handling and post-loop discovery.

These module-level helpers operate on a live ``Engine`` instance but
are kept out of the ``Engine`` class body so the orchestration code
stays focused on the main exploration loop. Mirrors the legacy
module-level layout (``_attempt_early_stopping_recovery``,
``_attempt_post_loop_coverage``).

Every function here respects the same boundaries:
- Uses only ``engine.config``, ``engine.constraints_to_solve``,
  ``engine.coverage_tracker``, ``engine._solve``, ``engine._run_iteration``,
  ``engine._snapshot`` — the narrow internal surface the recovery flow
  needs, not arbitrary engine internals.
- Dispatches via the provided ``Dispatcher`` rather than reaching
  through ``engine.plugins`` directly — matches the dispatch discipline
  used by the main loop.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from pyct.engine.plugin.dispatcher import Dispatcher
from pyct.engine.state import ExplorationState

if TYPE_CHECKING:
    from pyct.engine.engine import Engine


def handle_plateau(
    engine: Engine,
    state: ExplorationState,
    last_coverage_size: int,
    stale_count: int,
    input_queue: list[dict[str, Any]],
    dispatcher: Dispatcher,
    target: Callable,
    signature: inspect.Signature,
) -> int:
    """Track stale iterations; dispatch plateau event when stale hits threshold.

    Plateau dispatch is suppressed while the engine is replaying
    pre-queued seeds: during ``seed_phase``, stale iterations reflect
    uninformative seed execution rather than true exploration stalls.

    When the plateau fires, the pending constraint pool is cleared
    before dispatch: those constraints have produced no coverage gain
    for ``plateau_threshold`` consecutive iterations, so processing
    them further ahead of LLM-supplied seeds would waste budget.

    Plateau progress is measured against the wide scope count: when
    scope spans multiple files, growth in any of them resets stale.
    """
    if state.scope_observed_count > last_coverage_size:
        return 0

    stale_count += 1
    if stale_count < engine.config.plateau_threshold:
        return stale_count
    if state.seed_phase:
        return stale_count

    engine.constraints_to_solve.clear()
    state.coverage_at_last_plateau = state.scope_observed_count
    plateau_seeds = dispatcher.dispatch_collector(
        "on_coverage_plateau",
        engine._snapshot(target, signature, state),
    )
    input_queue.extend(plateau_seeds)
    # Plugin-supplied seeds get the same budget treatment as the
    # initial ones — they're a fresh replay batch, not engine
    # exploration.
    if plateau_seeds:
        state.seed_phase = True
    return 0


def check_plateau_outcome(engine: Engine, state: ExplorationState) -> None:
    """Evaluate whether the last plateau's seeds improved coverage.

    Called at the phase-boundary transition (seed_phase True -> False
    after a plateau dispatch). On improvement, the silencing counter
    resets; on repeated failure it climbs until
    ``max_stale_llm_attempts`` is reached, at which point the engine
    terminates with ``plateau_exhausted`` to bound LLM spend.
    """
    from pyct.engine.engine import _terminate

    baseline = state.coverage_at_last_plateau
    state.coverage_at_last_plateau = None
    if baseline is None:
        return

    if state.scope_observed_count > baseline:
        state.plateau_failure_count = 0
        return

    state.plateau_failure_count += 1
    if state.plateau_failure_count >= engine.config.max_stale_llm_attempts:
        _terminate(state, "plateau_exhausted")


def run_post_loop_discovery(
    engine: Engine,
    *,
    target: Callable,
    original_target: Callable,
    signature: inspect.Signature,
    initial_args: dict[str, Any],
    var_to_types: dict[str, str],
    state: ExplorationState,
    dispatcher: Dispatcher,
) -> None:
    """Close remaining coverage gaps after the main loop returns.

    Runs up to ``config.post_loop_rounds`` rounds of LLM-driven
    discovery. Each round dispatches ``on_post_loop_discovery``,
    executes the returned candidates, then runs a bounded solver
    mini-loop to exploit any fresh constraints. Silences after
    ``config.max_stale_llm_attempts`` consecutive non-improving
    rounds. Skipped entirely when coverage is already complete.
    """
    tracker = engine.coverage_tracker
    if tracker is None or tracker.is_fully_covered():
        return
    if engine.config.post_loop_rounds <= 0:
        return

    failure_count = 0
    for _ in range(engine.config.post_loop_rounds):
        if tracker.is_fully_covered():
            return
        coverage_before = state.scope_observed_count
        candidates = dispatcher.dispatch_collector(
            "on_post_loop_discovery",
            engine._snapshot(original_target, signature, state),
        )
        if not candidates:
            return
        _execute_post_loop_candidates(
            engine,
            candidates=candidates,
            target=target,
            initial_args=initial_args,
            var_to_types=var_to_types,
            state=state,
        )
        if state.scope_observed_count > coverage_before:
            failure_count = 0
            continue
        failure_count += 1
        if failure_count >= engine.config.max_stale_llm_attempts:
            return


def _execute_post_loop_candidates(
    engine: Engine,
    *,
    candidates: list[dict[str, Any]],
    target: Callable,
    initial_args: dict[str, Any],
    var_to_types: dict[str, str],
    state: ExplorationState,
) -> None:
    """Execute each candidate, then drive a bounded solver mini-loop."""
    for candidate in candidates:
        if candidate in state.inputs_tried:
            continue
        engine._run_iteration(target, candidate, state)
        state.inputs_tried.append(candidate)
        engine._fire_progress(state)

    remaining = engine.config.post_loop_mini_iterations
    tracker = engine.coverage_tracker
    while remaining > 0 and engine.constraints_to_solve:
        if tracker is not None and tracker.is_fully_covered():
            return
        constraint = engine.constraints_to_solve.pop(0)
        model, _status = engine._solve(constraint, var_to_types)
        if model is None:
            continue
        merged = {**initial_args, **model}
        if merged in state.inputs_tried:
            continue
        engine._run_iteration(target, merged, state)
        state.inputs_tried.append(merged)
        engine._fire_progress(state)
        remaining -= 1
