"""Engine — the concolic exploration orchestrator."""

from __future__ import annotations

import inspect
import logging
import time
from collections.abc import Callable
from typing import Any

from pyct.config.execution import ExecutionConfig
from pyct.engine.argument_resolver import build_var_to_types, wrap_arguments
from pyct.engine.coverage_tracker import CoverageTracker
from pyct.engine.function_inspector import inspect_target
from pyct.engine.line_tracer import line_tracer, lines_to_coverage_data
from pyct.engine.path import PathConstraintTracker
from pyct.engine.plugin.context import EngineContext
from pyct.engine.plugin.dispatcher import Dispatcher
from pyct.engine.plugin.protocol import Plugin
from pyct.engine.result import ExplorationResult
from pyct.engine.state import ExplorationState
from pyct.solver.solver import Solver
from pyct.utils.constraint import ConstraintRegistry

log = logging.getLogger("ct.engine")


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
    ) -> ExplorationResult:
        """Run concolic exploration on ``target`` starting from ``initial_args``.

        Returns an ExplorationResult describing the outcome. Termination
        reasons: ``full_coverage``, ``max_iterations``, ``timeout``,
        ``exhausted``, or ``error``. Target exceptions are captured in
        the result's ``error`` field; only engine-level failures (e.g.
        cannot inspect the target) mark ``success=False``.
        """
        ConstraintRegistry.clear()
        self.path = PathConstraintTracker()
        self.constraints_to_solve = []
        self.solver = Solver(
            solver=self.config.solver,
            timeout=self.config.solver_timeout,
        )

        try:
            return self._run(target, initial_args)
        except (TypeError, OSError) as e:
            return _error_result(f"cannot inspect target: {e}")
        finally:
            self.solver = None
            self.coverage_tracker = None

    def _run(
        self,
        target: Callable,
        initial_args: dict[str, Any],
    ) -> ExplorationResult:
        """Core exploration loop — inspect, dispatch, iterate, build result."""
        target_file, func_lines = inspect_target(target)
        self.coverage_tracker = CoverageTracker(target_file, func_lines)

        signature = inspect.signature(target)
        var_to_types = build_var_to_types(initial_args)
        dispatcher = Dispatcher(self.plugins)

        state = ExplorationState(
            start_time=time.monotonic(),
            total_lines=len(func_lines),
        )

        dispatcher.dispatch_observer(
            "on_exploration_start",
            self._snapshot(target, signature, state),
        )

        seeds = dispatcher.dispatch_collector(
            "on_seed_request",
            self._snapshot(target, signature, state),
        )
        input_queue: list[dict[str, Any]] = [dict(initial_args), *seeds]

        last_error = self._exploration_loop(
            target=target,
            target_file=target_file,
            signature=signature,
            initial_args=initial_args,
            var_to_types=var_to_types,
            state=state,
            input_queue=input_queue,
            dispatcher=dispatcher,
        )

        result = _build_result(state, last_error)
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
        target_file: str,
        signature: inspect.Signature,
        initial_args: dict[str, Any],
        var_to_types: dict[str, str],
        state: ExplorationState,
        input_queue: list[dict[str, Any]],
        dispatcher: Dispatcher,
    ) -> str | None:
        """Run the iteration loop; returns the last per-iteration error."""
        last_coverage_size = 0
        stale_count = 0
        last_error: str | None = None

        while not state.terminated:
            if self._check_budget(state):
                break

            args = self._next_input(input_queue, initial_args, var_to_types, state)
            if args is None:
                _terminate(state, "exhausted")
                break

            iteration_error = self._run_iteration(target, args, target_file, state)
            state.inputs_tried.append(args)
            state.iteration += 1

            if iteration_error is not None:
                last_error = iteration_error
                if iteration_error.startswith("timeout:"):
                    _terminate(state, "timeout")
                    break
            else:
                last_error = None

            if self.coverage_tracker is not None and self.coverage_tracker.is_fully_covered():
                _terminate(state, "full_coverage")
                break

            stale_count = self._handle_plateau(
                state,
                last_coverage_size,
                stale_count,
                input_queue,
                dispatcher,
                target,
                signature,
            )
            last_coverage_size = max(last_coverage_size, len(state.covered_lines))

        return last_error

    def _next_input(
        self,
        input_queue: list[dict[str, Any]],
        initial_args: dict[str, Any],
        var_to_types: dict[str, str],
        state: ExplorationState,
    ) -> dict[str, Any] | None:
        """Return the next unseen input, either from the queue or by solving."""
        while input_queue:
            args = input_queue.pop(0)
            if args not in state.inputs_tried:
                return args

        while self.constraints_to_solve:
            constraint = self.constraints_to_solve.pop(0)
            model = self._solve(constraint, var_to_types)
            if model is None:
                continue
            merged = {**initial_args, **model}
            if merged not in state.inputs_tried:
                return merged

        return None

    def _solve(
        self,
        constraint: Any,
        var_to_types: dict[str, str],
    ) -> dict[str, Any] | None:
        """Call the solver and return the model, or None on UNSAT/UNKNOWN."""
        assert self.solver is not None
        model, _status, _error = self.solver.find_model(constraint, var_to_types)
        return model

    def _run_iteration(
        self,
        target: Callable,
        args: dict[str, Any],
        target_file: str,
        state: ExplorationState,
    ) -> str | None:
        """Run one concolic iteration with tracing; return error string or None."""
        assert self.coverage_tracker is not None

        self.path.reset()
        concolic_args = wrap_arguments(args, self)
        deadline = state.start_time + self.config.timeout_seconds

        error: str | None = None
        with line_tracer(target_file, deadline=deadline) as hit_lines:
            try:
                target(**concolic_args)
            except TimeoutError as e:
                error = f"timeout: {e}"
            except SystemExit as e:
                error = f"SystemExit({e.code})"
            except Exception as e:
                error = f"{type(e).__name__}: {e}"

        data = lines_to_coverage_data(target_file, hit_lines)
        self.coverage_tracker.update(data)
        state.covered_lines |= self.coverage_tracker.covered_lines

        if error is not None:
            log.debug("Target iteration raised: %s", error)
        return error

    def _check_budget(self, state: ExplorationState) -> bool:
        """Check max-iterations and wall-clock timeout; terminate if exceeded."""
        if state.iteration >= self.config.max_iterations:
            _terminate(state, "max_iterations")
            return True
        if state.elapsed_seconds() >= self.config.timeout_seconds:
            _terminate(state, "timeout")
            return True
        return False

    def _handle_plateau(
        self,
        state: ExplorationState,
        last_coverage_size: int,
        stale_count: int,
        input_queue: list[dict[str, Any]],
        dispatcher: Dispatcher,
        target: Callable,
        signature: inspect.Signature,
    ) -> int:
        """Track stale iterations; dispatch plateau event and reset if needed."""
        if len(state.covered_lines) > last_coverage_size:
            return 0

        stale_count += 1
        if stale_count < self.config.plateau_threshold:
            return stale_count

        plateau_seeds = dispatcher.dispatch_collector(
            "on_coverage_plateau",
            self._snapshot(target, signature, state),
        )
        input_queue.extend(plateau_seeds)
        return 0

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
            inputs_tried=tuple(state.inputs_tried),
            target_function=target,
            target_signature=signature,
            config=self.config,
            elapsed_seconds=state.elapsed_seconds(),
        )


def _terminate(state: ExplorationState, reason: str) -> None:
    """Mark the exploration as terminated with the given reason."""
    state.terminated = True
    state.termination_reason = reason


def _build_result(
    state: ExplorationState,
    last_error: str | None,
) -> ExplorationResult:
    """Turn the final state into an ExplorationResult."""
    return ExplorationResult(
        success=True,
        coverage_percent=state.coverage_percent(),
        executed_lines=frozenset(state.covered_lines),
        paths_explored=state.paths_explored(),
        iterations=state.iteration,
        termination_reason=state.termination_reason or "exhausted",
        elapsed_seconds=state.elapsed_seconds(),
        error=last_error,
        inputs_generated=tuple(state.inputs_tried),
    )


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
