"""Engine — the concolic exploration orchestrator."""

from __future__ import annotations

import inspect
import logging
import time
from collections.abc import Callable
from typing import Any

from pyct.config.execution import ExecutionConfig
from pyct.engine.ast_transformer import rewrite_target
from pyct.engine.binding import (
    Leaf,
    apply_model,
    binding_var_types,
    build_binding,
    wrap_leaves,
)
from pyct.engine.constraint_optimizer import optimize
from pyct.engine.coverage_scope import CoverageScope
from pyct.engine.coverage_tracker import CoverageTracker
from pyct.engine.environment import prepared_environment
from pyct.engine.line_tracer import line_tracer, lines_to_coverage_data
from pyct.engine.path import PathConstraintTracker
from pyct.engine.plugin.context import EngineContext
from pyct.engine.plugin.dispatcher import Dispatcher
from pyct.engine.plugin.protocol import Plugin
from pyct.engine.recovery import (
    check_plateau_outcome,
    handle_plateau,
    run_post_loop_discovery,
)
from pyct.engine.result import ExplorationResult
from pyct.engine.state import ChainStats, ExplorationState
from pyct.engine.types import InputRecord, Outcome, Provenance
from pyct.solver.executor import SolverStatus
from pyct.solver.solver import Solver
from pyct.utils.call_binding import call_with_args
from pyct.utils.constraint import ConstraintRegistry

log = logging.getLogger("ct.engine")

TIMEOUT_ERROR_PREFIX = "timeout:"
_UNPRODUCTIVE_STREAK_THRESHOLD = 3


class Engine:
    """Orchestrates concolic exploration of a target function.

    Plugins are registered via ``engine.register(plugin_instance)``
    and receive events during the exploration loop. See
    ``pyct.engine.plugin`` documentation for event semantics.

    Engine instances are NOT thread-safe. The Concolic type layer
    reaches back through ``engine.path`` / ``engine.constraints_to_solve``
    when branches fire, so concurrent ``explore()`` calls on the same
    instance would race on that state. Use one Engine per concurrent
    caller — the benchmark runner and CLI already do this by virtue of
    running in separate processes.

    Example::

        from pyct import Engine, ExecutionConfig
        engine = Engine(ExecutionConfig(max_iterations=50))
        result = engine.explore(my_target, {"x": 0})
    """

    def __init__(self, config: ExecutionConfig):
        self.config = config
        self.plugins: list[Plugin] = []
        self.path: PathConstraintTracker = PathConstraintTracker()
        self.constraints_to_solve: list[Any] = []
        self.solver: Solver | None = None
        self.coverage_tracker: CoverageTracker | None = None
        # ``state`` is published here so helpers reached via
        # ``concolic_value.engine`` (e.g. ``core/str/helpers.py`` substr
        # emission) can walk back to live counters without threading
        # state through every call site. Stays None outside an active
        # ``explore()`` call.
        self.state: ExplorationState | None = None
        # Maps solver variables to the primitive leaves they stand for
        # inside dict / list / object arguments. Built once per run from
        # the seed arguments, since the argument shape is fixed for the
        # run and only leaf values change. Empty outside ``explore()``.
        self._binding: tuple[Leaf, ...] = ()
        # Chain ID of the constraint whose solver model fed the most
        # recent iteration; consumed by ``_post_iteration_update`` to
        # attribute the iteration's coverage delta back to the chain.
        # None when the iteration came from a seed or a non-chain
        # constraint, leaving the chain stats untouched.
        self._last_picked_chain_id: int | None = None
        self._progress_callback: Callable[[Engine, ExplorationState], None] | None = None
        self._iteration_start_callback: (
            Callable[[Engine, ExplorationState, dict[str, Any], Provenance], None] | None
        ) = None

    def register(self, plugin: Plugin) -> None:
        """Register a plugin instance with the engine.

        Plugins are ordered by their ``priority`` attribute (lower
        runs earlier), with registration order as a tiebreaker.
        """
        self.plugins.append(plugin)

    def explore(
        self,
        target: Callable,
        initial_args: dict[str, Any],
        *,
        seed_inputs: list[dict[str, Any]] | None = None,
        plugins: list[Plugin] | None = None,
        progress_callback: Callable[[Engine, ExplorationState], None] | None = None,
        iteration_start_callback: (
            Callable[[Engine, ExplorationState, dict[str, Any], Provenance], None] | None
        ) = None,
    ) -> ExplorationResult:
        """Run concolic exploration on ``target`` starting from ``initial_args``.

        Args:
            seed_inputs: Pre-generated seed inputs to prepend to the input
                queue. When provided (even if empty), the engine skips its
                own ``on_seed_request`` dispatch — the caller has already
                obtained seeds and is supplying them directly.
            plugins: Plugin instances to register before exploration starts.
                These are in addition to any previously registered via
                ``engine.register()``.
            progress_callback: Invoked after every completed iteration
                with ``(engine, state)``. ``state.iteration`` and
                ``state.records`` reflect the just-completed
                iteration. Used by the isolated runner to checkpoint
                partial progress over its pipe so watchdog kills can
                fall back to the latest snapshot instead of dropping
                all concolic-loop coverage.
            iteration_start_callback: Invoked just before every target
                call with ``(engine, state, args, provenance)``. Pairs
                with ``progress_callback`` for the isolated runner's
                tombstone protocol: the runner writes an ``iter_start``
                message to its pipe so a watchdog kill mid-iteration
                can be reconstructed by the parent as a TIMEOUT record
                using the args/provenance the engine was about to run.

        Returns an ExplorationResult describing the outcome. Termination
        reasons: ``full_coverage``, ``max_iterations``, ``timeout``,
        ``exhausted``, or ``error``. Target exceptions are captured in
        the result's ``error`` field; only engine-level failures (e.g.
        cannot inspect the target) mark ``success=False``.
        """
        if plugins:
            for plugin in plugins:
                self.register(plugin)

        self._progress_callback = progress_callback
        self._iteration_start_callback = iteration_start_callback

        ConstraintRegistry.clear()
        self.path = PathConstraintTracker()
        self.constraints_to_solve = []
        self.solver = Solver(
            solver=self.config.solver,
            timeout=self.config.solver_timeout,
        )

        try:
            with prepared_environment():
                return self._run(target, initial_args, seed_inputs=seed_inputs)
        except (TypeError, OSError) as e:
            return _error_result(f"cannot inspect target: {e}")
        finally:
            self.solver = None
            self.coverage_tracker = None
            self.state = None
            self._binding = ()

    def _run(
        self,
        target: Callable,
        initial_args: dict[str, Any],
        *,
        seed_inputs: list[dict[str, Any]] | None = None,
    ) -> ExplorationResult:
        """Core exploration loop — inspect, dispatch, iterate, build result."""
        scope = self.config.scope or CoverageScope.for_target(target)
        target_file = scope.target_file
        func_lines = scope.executable_lines[target_file]
        self.coverage_tracker = CoverageTracker(scope)

        signature = inspect.signature(target)
        self._binding = build_binding(initial_args)
        var_to_types = binding_var_types(self._binding)
        dispatcher = Dispatcher(self.plugins)

        state = ExplorationState(
            start_time=time.monotonic(),
            total_lines=len(func_lines),
            tracker=self.coverage_tracker,
        )
        self.state = state
        rewritten_target = _try_rewrite(target, state)
        state.covered_lines |= self.coverage_tracker.covered_lines
        state.observed_lines |= self.coverage_tracker.observed_lines
        # Snapshot covered_lines before the loop runs so result consumers
        # can verify ``∪ record.new_lines == executed_lines − pre_cover_lines``
        # without re-running the engine.
        state.pre_cover_lines = frozenset(state.covered_lines)

        dispatcher.dispatch_observer(
            "on_exploration_start",
            self._snapshot(target, signature, state),
        )

        if seed_inputs is not None:
            seed_provenance = Provenance.SEED
            seeds = list(seed_inputs)
        else:
            seed_provenance = Provenance.PLUGIN_SEED
            seeds = dispatcher.dispatch_collector(
                "on_seed_request",
                self._snapshot(target, signature, state),
            )
        input_queue: list[tuple[dict[str, Any], Provenance]] = [
            (dict(initial_args), Provenance.SEED),
            *((dict(s), seed_provenance) for s in seeds),
        ]

        last_error = self._exploration_loop(
            target=rewritten_target,
            original_target=target,
            signature=signature,
            initial_args=initial_args,
            var_to_types=var_to_types,
            state=state,
            input_queue=input_queue,
            dispatcher=dispatcher,
        )

        run_post_loop_discovery(
            self,
            target=rewritten_target,
            original_target=target,
            signature=signature,
            initial_args=initial_args,
            var_to_types=var_to_types,
            state=state,
            dispatcher=dispatcher,
        )

        result = _build_result(state, last_error, plugins=self.plugins)
        dispatcher.dispatch_observer(
            "on_exploration_end",
            self._snapshot(target, signature, state),
            result,
        )
        return result

    def _exploration_loop(
        self,
        *,
        target: Callable,
        original_target: Callable,
        signature: inspect.Signature,
        initial_args: dict[str, Any],
        var_to_types: dict[str, str],
        state: ExplorationState,
        input_queue: list[tuple[dict[str, Any], Provenance]],
        dispatcher: Dispatcher,
    ) -> str | None:
        """Run the iteration loop; returns the last per-iteration error."""
        last_coverage_size = 0
        stale_count = 0
        last_error: str | None = None

        while not state.terminated:
            if self._check_budget(state):
                break

            next_input = self._next_input(
                input_queue=input_queue,
                initial_args=initial_args,
                var_to_types=var_to_types,
                state=state,
                dispatcher=dispatcher,
                target=original_target,
                signature=signature,
            )
            if next_input is None:
                _terminate(state, "exhausted")
                break

            args, provenance = next_input
            picked_chain_id = self._last_picked_chain_id
            self._fire_iteration_start(state, args, provenance)
            covered_before = frozenset(state.observed_lines)
            iteration_error = self._run_iteration(target, args, state)
            new_lines = frozenset(state.observed_lines) - covered_before
            self._post_iteration_update(picked_chain_id, len(new_lines))
            state.records.append(build_record(args, provenance, iteration_error, new_lines))
            state.iteration += 1
            self._fire_progress(state)

            if iteration_error is not None:
                last_error = iteration_error
                # A timeout during seed phase is the per-seed soft
                # deadline firing — skip this seed, keep the queue
                # draining. The global ``timeout_seconds`` only takes
                # effect once exploration begins.
                if iteration_error.startswith("timeout:") and not state.seed_phase:
                    _terminate(state, "timeout")
                    break
            else:
                last_error = None

            if (
                self.coverage_tracker is not None
                and self.coverage_tracker.is_fully_covered()
                and not self._has_pending_chain_constraints()
            ):
                _terminate(state, "full_coverage")
                break

            # Measure the previous plateau's outcome before a new plateau
            # can fire — otherwise a repeat dispatch would overwrite the
            # recorded baseline and skip the silencing counter update.
            if state.coverage_at_last_plateau is not None and not state.seed_phase:
                check_plateau_outcome(self, state)
                if state.terminated:
                    break

            stale_count = handle_plateau(
                self,
                state,
                last_coverage_size,
                stale_count,
                input_queue,
                dispatcher,
                target,
                signature,
            )
            last_coverage_size = max(last_coverage_size, state.scope_observed_count)

        return last_error

    def _next_input(
        self,
        *,
        input_queue: list[tuple[dict[str, Any], Provenance]],
        initial_args: dict[str, Any],
        var_to_types: dict[str, str],
        state: ExplorationState,
        dispatcher: Dispatcher,
        target: Callable,
        signature: inspect.Signature,
    ) -> tuple[dict[str, Any], Provenance] | None:
        """Return the next unseen input plus its provenance from the queue,
        solver, or resolver plugins."""
        while input_queue:
            args, provenance = input_queue.pop(0)
            if not state.has_seen_args(args):
                self._last_picked_chain_id = None
                return args, provenance

        # Queue fully drained — seed phase is over; subsequent iterations
        # come from the solver or resolver plugins and must respect the
        # exploration budget.
        state.seed_phase = False
        # Iterations driven by the queue carry no chain attribution.
        self._last_picked_chain_id = None

        while self.constraints_to_solve:
            constraint = self._pick_next_constraint()
            if constraint is None:
                break
            self._last_picked_chain_id = getattr(constraint, "chain_id", None)
            solved_args, status = self._solve(constraint, var_to_types, initial_args)

            if state.elapsed_seconds() >= self.config.timeout_seconds:
                _terminate(state, "timeout")
                return None

            if solved_args is not None:
                if not state.has_seen_args(solved_args):
                    return solved_args, Provenance.SOLVER
                continue

            if status == SolverStatus.UNSAT:
                state.gen_unsat += 1
                continue

            # UNKNOWN / ERROR: count raw, regardless of whether a plugin
            # resolver later supplies an alternate input.
            state.gen_unknown += 1
            resolution = dispatcher.dispatch_resolver(
                "on_constraint_unknown",
                self._snapshot(target, signature, state),
                constraint,
            )
            if resolution is not None:
                merged = {**initial_args, **resolution}
                if not state.has_seen_args(merged):
                    return merged, Provenance.PLUGIN_UNKNOWN

        return None

    def _solve(
        self,
        constraint: Any,
        var_to_types: dict[str, str],
        base_args: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, SolverStatus]:
        """Call the solver and return ``(args, status)``.

        ``args`` is a complete argument dict — the solver's model applied
        onto ``base_args`` through the binding table — populated when
        status is SAT and None on UNSAT/UNKNOWN/ERROR. Callers use the
        status to decide whether to fall back to a resolver plugin:
        UNSAT means provably unreachable and is not retryable, while
        UNKNOWN/ERROR may be solvable by an LLM or fuzzing strategy.

        Applying here rather than at each call site means both solver
        paths — the main loop and post-loop discovery — get nested values
        written back, instead of the flat model leaking through as
        stray top-level keys that ``call_with_args`` would silently drop.
        """
        assert self.solver is not None
        constraint = optimize(constraint, self.state)
        model, status, _error = self.solver.find_model(constraint, var_to_types)
        if model is None:
            return None, status
        return apply_model(base_args, self._binding, model), status

    def _run_iteration(
        self,
        target: Callable,
        args: dict[str, Any],
        state: ExplorationState,
    ) -> str | None:
        """Run one concolic iteration with tracing; return error string or None.

        ``wrap_leaves`` runs inside the containment scope so a Concolic
        constructor failure on one seed aborts only that iteration — not
        the whole exploration. Without this guard the exception escapes
        past ``explore()``'s narrow ``(TypeError, OSError)`` filter into
        ``_child_entry``, which nukes the subprocess and drops every
        remaining seed.
        """
        assert self.coverage_tracker is not None

        self.path.reset()
        try:
            concolic_args = wrap_leaves(args, self._binding, self)
        except Exception as e:
            state.harness_error += 1
            log.debug("wrap_leaves failed for %r: %s", args, e)
            return f"wrap_leaves: {type(e).__name__}: {e}"

        deadline = self._iteration_deadline(state)
        scope_files = self.coverage_tracker.scope.files
        error: str | None = None
        with line_tracer(scope_files, deadline=deadline) as hit_lines:
            try:
                call_with_args(target, concolic_args)
            except TimeoutError as e:
                error = f"timeout: {e}"
            except SystemExit as e:
                error = f"SystemExit({e.code})"
            except Exception as e:
                error = f"{type(e).__name__}: {e}"

        data = lines_to_coverage_data(hit_lines)
        self.coverage_tracker.update(data)
        state.covered_lines |= self.coverage_tracker.covered_lines
        state.observed_lines |= self.coverage_tracker.observed_lines

        if error is not None:
            log.debug("Target iteration raised: %s", error)
        return error

    def _check_budget(self, state: ExplorationState) -> bool:
        """Check max-iterations and wall-clock timeout; terminate if exceeded.

        During seed phase the per-iteration budget is the only safety
        limit — ``max_iterations`` and global ``timeout_seconds`` are
        deferred until every supplied seed has run. Otherwise an LLM
        returning more seeds than ``max_iterations``, or a slow target
        mid-seed, would strand the tail of the queue.
        """
        if state.seed_phase:
            return False
        if state.iteration >= self.config.max_iterations:
            _terminate(state, "max_iterations")
            return True
        if state.elapsed_seconds() >= self.config.timeout_seconds:
            _terminate(state, "timeout")
            return True
        return False

    def _iteration_deadline(self, state: ExplorationState) -> float:
        """Return the wall-clock deadline for the next target call.

        Seed-phase iterations use ``seed_soft_timeout`` so a slow seed
        cannot eat the global budget. Post-seed iterations use the
        classic exploration deadline so the engine's own generated
        inputs share one shared pool.
        """
        if state.seed_phase:
            return time.monotonic() + self.config.seed_soft_timeout
        return state.start_time + self.config.timeout_seconds

    def _fire_progress(self, state: ExplorationState) -> None:
        """Invoke the optional progress callback, swallowing any failure.

        The callback runs in the same process and iteration loop as
        exploration; a buggy callback must not corrupt engine state or
        abort the run. Callers that need strict delivery (e.g. the
        isolated runner) should log or re-raise inside their own
        callback instead.
        """
        if self._progress_callback is None:
            return
        try:
            self._progress_callback(self, state)
        except Exception:  # noqa: BLE001 — protect the engine loop
            log.exception("progress_callback raised; ignoring")

    def _fire_iteration_start(
        self,
        state: ExplorationState,
        args: dict[str, Any],
        provenance: Provenance,
    ) -> None:
        """Invoke the optional iteration-start callback before ``_run_iteration``.

        Mirrors ``_fire_progress``'s error-containment policy — a buggy
        callback must not abort exploration. The callback receives the
        args and provenance the engine is about to run so a tombstone
        consumer (the isolated runner) can record what would have
        happened if the iteration is killed before it completes.
        """
        if self._iteration_start_callback is None:
            return
        try:
            self._iteration_start_callback(self, state, args, provenance)
        except Exception:  # noqa: BLE001 — protect the engine loop
            log.exception("iteration_start_callback raised; ignoring")

    def _has_pending_chain_constraints(self) -> bool:
        """Return True when any pending constraint still belongs to a chain.

        The full-coverage termination check defers when a chain still
        has un-processed disjuncts so the adaptive scheduler can flip
        them — without this, the seed iteration's coverage of the
        rewritten ``return x in {…}`` line would terminate exploration
        before the chain's unproductive-streak counter could fire.
        """
        return any(getattr(c, "chain_id", None) is not None for c in self.constraints_to_solve)

    def _pick_next_constraint(self) -> Any | None:
        """Return the next constraint to solve, ordered by chain priority.

        Non-chain constraints are popped first, then chain constraints
        whose ``unproductive_streak`` is below the deprioritization
        threshold, then deprioritized chain constraints as a
        last-resort fallback. Returns ``None`` when the pool is empty.
        The returned constraint is removed from ``constraints_to_solve``.
        """
        if not self.constraints_to_solve:
            return None
        stats = self.state.or_chain_stats if self.state is not None else {}
        for index, candidate in enumerate(self.constraints_to_solve):
            if getattr(candidate, "chain_id", None) is None:
                return self.constraints_to_solve.pop(index)
        for index, candidate in enumerate(self.constraints_to_solve):
            chain_id = getattr(candidate, "chain_id", None)
            if not _is_deprioritized(stats.get(chain_id)):
                return self.constraints_to_solve.pop(index)
        return self.constraints_to_solve.pop(0)

    def _post_iteration_update(self, chain_id: int | None, new_lines_covered: int) -> None:
        """Attribute the iteration's coverage delta back to the picked chain.

        No-op when the iteration consumed a non-chain constraint or
        ``state`` is not attached. Bumps ``attempted_flips`` then either
        records a productive flip (resetting ``unproductive_streak``) or
        an unproductive one; the first crossing of the threshold for a
        chain ticks ``gen_chain_deprioritized`` exactly once.
        """
        if chain_id is None or self.state is None:
            return
        stats = self.state.or_chain_stats.setdefault(chain_id, ChainStats())
        was_deprioritized = _is_deprioritized(stats)
        stats.attempted_flips += 1
        if new_lines_covered > 0:
            stats.productive_flips += 1
            stats.unproductive_streak = 0
            return
        stats.unproductive_streak += 1
        if not was_deprioritized and _is_deprioritized(stats):
            self.state.gen_chain_deprioritized += 1

    def _snapshot(
        self,
        target: Callable,
        signature: inspect.Signature,
        state: ExplorationState,
    ) -> EngineContext:
        """Build an immutable EngineContext for plugin dispatch."""
        return EngineContext(
            iteration=state.iteration,
            constraint_pool=tuple(self.constraints_to_solve),
            covered_lines=frozenset(state.covered_lines),
            total_lines=state.total_lines,
            inputs_tried=tuple(record.args for record in state.records),
            target_function=target,
            target_signature=signature,
            config=self.config,
            elapsed_seconds=state.elapsed_seconds(),
        )


def _is_deprioritized(stats: ChainStats | None) -> bool:
    """Return True when ``stats`` has crossed the unproductive-streak threshold."""
    return stats is not None and stats.unproductive_streak >= _UNPRODUCTIVE_STREAK_THRESHOLD


def classify_outcome(iteration_error: str | None, new_lines: frozenset[int]) -> Outcome:
    """Classify an iteration's result into one of the four Outcome values.

    Outcome rules (mutually exclusive, error wins over coverage gain):
    - ``TIMEOUT`` when the iteration error is a tracer-deadline timeout.
    - ``TARGET_ERROR`` for any other non-None error string (target raise,
      wrap_leaves failure, SystemExit). The non-execution-counters
      sub-task may later split harness errors out into their own counter,
      but for record classification any non-timeout error is TARGET_ERROR.
    - ``COVERED_NEW`` when the iteration completed cleanly and traced at
      least one previously-unseen line.
    - ``NO_GAIN`` when the iteration completed cleanly and traced only
      duplicate lines.
    """
    if iteration_error is None:
        return Outcome.COVERED_NEW if new_lines else Outcome.NO_GAIN
    if iteration_error.startswith(TIMEOUT_ERROR_PREFIX):
        return Outcome.TIMEOUT
    return Outcome.TARGET_ERROR


def build_record(
    args: dict[str, Any],
    provenance: Provenance,
    iteration_error: str | None,
    new_lines: frozenset[int],
) -> InputRecord:
    """Build an InputRecord with classified outcome and stored error.

    ``error`` is preserved on TARGET_ERROR / TIMEOUT records so consumers
    can distinguish failure modes; clean outcomes carry ``None``.
    ``new_lines`` is independent of outcome — TARGET_ERROR / TIMEOUT
    records keep the lines traced before the failure.
    """
    outcome = classify_outcome(iteration_error, new_lines)
    error = iteration_error if outcome in (Outcome.TARGET_ERROR, Outcome.TIMEOUT) else None
    return InputRecord(
        args=args,
        provenance=provenance,
        outcome=outcome,
        new_lines=new_lines,
        error=error,
    )


def _try_rewrite(target: Callable, state: ExplorationState | None = None) -> Callable:
    """Attempt AST rewrite; fall back to original on exec failures.

    The AST transformer breaks on:
    - External library functions with wrong __globals__ (NameError)
    - Class targets where source is ``class Foo:`` not ``def foo:`` (TypeError)
    - Decorated functions with missing attributes (AttributeError)

    Falls back to the original target, losing int/str/range/is rewriting
    but letting the engine explore with plain Concolic wrapping.

    Lambda rejection still raises — lambdas have fundamental issues
    (inspect.getsource returns the containing line, causing recursion).

    The optional ``state`` argument flows to the Compare rewriter so its
    membership-rewrite firing / skip counters tick on the live exploration
    state. Test callers that pass no state get the same rewrites without
    counter side effects.
    """
    name = getattr(target, "__name__", "")
    if name == "<lambda>":
        from pyct.engine.ast_transformer import rewrite_target as _rw

        return _rw(target, state)  # will raise TypeError for lambdas
    try:
        return rewrite_target(target, state)
    except (TypeError, NameError, KeyError, AttributeError, OSError) as e:
        log.debug("AST rewrite failed for %s, using original: %s", name, e)
        return target


def _terminate(state: ExplorationState, reason: str) -> None:
    """Mark the exploration as terminated with the given reason."""
    state.terminated = True
    state.termination_reason = reason


def _build_result(
    state: ExplorationState,
    last_error: str | None,
    *,
    plugins: list[Plugin] | None = None,
) -> ExplorationResult:
    """Turn the final state into an ExplorationResult.

    ``executed_lines`` reports tracer-observed lines in the target's own
    file only (narrow) — pre-covered headers are kept in
    ``state.covered_lines`` for plateau/percent accounting but would
    otherwise shadow the first body line and break downstream def-header
    backfill (``_build_coverage_result`` in tools/benchmark/runners.py).
    Callers can re-derive header coverage from source statements.

    ``scope_executed_lines`` reports the wide view as ``(file, line)``
    tuples across every file in the engine's CoverageScope — the paper's
    dual-reporting signal that pairs with the benchmark's post-hoc
    rerun measurement.

    ``gen_parse_failed`` is a soft-convention sweep: the engine sums
    ``parse_failed`` across every plugin that exposes the attribute. The
    LLM plugin populates it via its parser tuple-return; other plugins
    may opt in by carrying the same attribute name.
    """
    scope_lines, scope_total, scope_percent = _scope_snapshot(state)
    gen_parse_failed = sum(getattr(p, "parse_failed", 0) for p in plugins or ())
    return ExplorationResult(
        success=True,
        coverage_percent=state.coverage_percent(),
        executed_lines=frozenset(state.observed_lines),
        paths_explored=state.paths_explored(),
        iterations=state.iteration,
        termination_reason=state.termination_reason or "exhausted",
        elapsed_seconds=state.elapsed_seconds(),
        error=last_error,
        inputs_generated=tuple(state.records),
        scope_coverage_percent=scope_percent,
        scope_executed_lines=scope_lines,
        scope_total_lines=scope_total,
        pre_cover_lines=state.pre_cover_lines,
        gen_unsat=state.gen_unsat,
        gen_unknown=state.gen_unknown,
        gen_parse_failed=gen_parse_failed,
        gen_substr_let_bound=state.gen_substr_let_bound,
        gen_count_rewritten=state.gen_count_rewritten,
        gen_count_skipped_symbolic_sub=state.gen_count_skipped_symbolic_sub,
        gen_membership_rewritten=state.gen_membership_rewritten,
        gen_membership_skipped_non_literal=state.gen_membership_skipped_non_literal,
        gen_str_to_int_singleton_rewritten=state.gen_str_to_int_singleton_rewritten,
        gen_case_fold_rewritten=state.gen_case_fold_rewritten,
        gen_case_fold_skipped_non_ascii=state.gen_case_fold_skipped_non_ascii,
        gen_chain_deprioritized=state.gen_chain_deprioritized,
        harness_error=state.harness_error,
    )


def _scope_snapshot(
    state: ExplorationState,
) -> tuple[frozenset[tuple[str, int]], int, float]:
    """Return the wide-view snapshot (line pairs, total, percent) from state."""
    tracker = state.tracker
    if tracker is None:
        return frozenset(), 0, 0.0
    pairs = frozenset(
        (path, line) for path, lines in tracker.observed_by_file.items() for line in lines
    )
    return pairs, tracker.total_lines, tracker.coverage_percent


def _error_result(message: str) -> ExplorationResult:
    """Build a result representing an engine-level failure."""
    return ExplorationResult(
        success=False,
        coverage_percent=0.0,
        executed_lines=frozenset(),
        paths_explored=0,
        iterations=0,
        termination_reason="error",
        elapsed_seconds=0.0,
        error=message,
    )
