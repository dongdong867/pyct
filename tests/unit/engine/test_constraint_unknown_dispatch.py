"""Tests for on_constraint_unknown resolver dispatch in Engine._next_input.

When the SMT solver returns UNKNOWN or ERROR on a constraint, the
engine dispatches ``on_constraint_unknown`` to registered plugins as a
resolver event (first non-None wins). This lets plugins — LLM, fuzzing,
future strategies — provide a fallback input when the solver can't.

UNSAT is NOT a trigger: an unsatisfiable constraint means the branch is
provably unreachable, and no amount of plugin help can satisfy it.
Dispatching on UNSAT would waste plugin capacity on dead paths.

Tests cover:
- Happy: UNKNOWN status fires the resolver; its Resolution becomes the
  next input
- Edge: resolver returns None → engine falls through to the next
  constraint in the queue
- Negative: UNSAT status does NOT fire the resolver
- Negative: SAT status does NOT fire the resolver (the model wins)
"""

from __future__ import annotations

from typing import Any


class _StubSolver:
    """Minimal solver stub that returns a scripted sequence of results.

    Each call to ``find_model`` pops the next entry from ``responses``.
    Each response is ``(model, status)`` where ``status`` is one of
    ``"sat"``, ``"unsat"``, ``"unknown"``, ``"error"``.
    """

    def __init__(self, responses: list[tuple[dict[str, Any] | None, str]]):
        self._responses = list(responses)
        self.calls: list[Any] = []

    def find_model(self, constraint: Any, var_to_types: dict[str, Any]) -> tuple[Any, Any, str]:
        from pyct.solver.executor import SolverStatus

        self.calls.append(constraint)
        model, status_name = self._responses.pop(0)
        status = SolverStatus(status_name)
        return model, status, ""

    def validate_expression(self, expr: Any, value: Any) -> Any:
        return None


class _RecordingPlugin:
    """Test plugin that records on_constraint_unknown calls.

    If ``resolution`` is set, returns it as the resolver response.
    Otherwise returns None.
    """

    def __init__(self, name: str = "recorder", resolution: dict[str, Any] | None = None):
        self.name = name
        self.priority = 100
        self.resolution = resolution
        self.unknown_calls: list[Any] = []

    def on_constraint_unknown(self, ctx: Any, constraint: Any) -> dict[str, Any] | None:
        self.unknown_calls.append(constraint)
        return self.resolution


def _simple_target(x: int) -> int:
    if x > 0:
        return 1
    return 0


def _build_engine_with_queue(solver_responses, plugin):
    """Return (engine, dispatcher, state, signature) ready for _next_input."""
    import inspect
    import time

    from pyct.config.execution import ExecutionConfig
    from pyct.engine.engine import Engine
    from pyct.engine.plugin.dispatcher import Dispatcher
    from pyct.engine.state import ExplorationState

    engine = Engine(ExecutionConfig())
    engine.solver = _StubSolver(solver_responses)
    engine.constraints_to_solve = ["(> x_VAR 0)", "(< x_VAR 0)"]
    engine.register(plugin)

    state = ExplorationState(start_time=time.monotonic(), total_lines=3)
    dispatcher = Dispatcher(engine.plugins)
    signature = inspect.signature(_simple_target)

    return engine, dispatcher, state, signature


class TestConstraintUnknownDispatch:
    def test_unknown_status_fires_resolver_and_uses_resolution(self):
        from pyct.engine.engine import Engine

        plugin = _RecordingPlugin(resolution={"x": 42})
        engine, dispatcher, state, signature = _build_engine_with_queue(
            [(None, "unknown")],
            plugin,
        )
        engine.constraints_to_solve = ["(> x_VAR 0)"]

        result = Engine._next_input(
            engine,
            input_queue=[],
            initial_args={"x": 0},
            var_to_types={"x_VAR": "Int"},
            state=state,
            dispatcher=dispatcher,
            target=_simple_target,
            signature=signature,
        )

        assert plugin.unknown_calls == ["(> x_VAR 0)"]
        assert result == {"x": 42}

    def test_unsat_status_does_not_fire_resolver(self):
        from pyct.engine.engine import Engine

        plugin = _RecordingPlugin(resolution={"x": 99})
        engine, dispatcher, state, signature = _build_engine_with_queue(
            [(None, "unsat")],
            plugin,
        )
        engine.constraints_to_solve = ["(> x_VAR 0)"]

        result = Engine._next_input(
            engine,
            input_queue=[],
            initial_args={"x": 0},
            var_to_types={"x_VAR": "Int"},
            state=state,
            dispatcher=dispatcher,
            target=_simple_target,
            signature=signature,
        )

        assert plugin.unknown_calls == []
        assert result is None  # nothing left to try

    def test_sat_status_uses_solver_model_not_resolver(self):
        from pyct.engine.engine import Engine

        plugin = _RecordingPlugin(resolution={"x": 99})
        engine, dispatcher, state, signature = _build_engine_with_queue(
            [({"x": 7}, "sat")],
            plugin,
        )
        engine.constraints_to_solve = ["(> x_VAR 0)"]

        result = Engine._next_input(
            engine,
            input_queue=[],
            initial_args={"x": 0},
            var_to_types={"x_VAR": "Int"},
            state=state,
            dispatcher=dispatcher,
            target=_simple_target,
            signature=signature,
        )

        assert plugin.unknown_calls == []
        assert result == {"x": 7}

    def test_resolver_returning_none_falls_through_to_next_constraint(self):
        from pyct.engine.engine import Engine

        plugin = _RecordingPlugin(resolution=None)
        engine, dispatcher, state, signature = _build_engine_with_queue(
            [(None, "unknown"), ({"x": 11}, "sat")],
            plugin,
        )
        engine.constraints_to_solve = ["(> x_VAR 0)", "(< x_VAR 0)"]

        result = Engine._next_input(
            engine,
            input_queue=[],
            initial_args={"x": 0},
            var_to_types={"x_VAR": "Int"},
            state=state,
            dispatcher=dispatcher,
            target=_simple_target,
            signature=signature,
        )

        assert plugin.unknown_calls == ["(> x_VAR 0)"]
        assert result == {"x": 11}

    def test_error_status_also_fires_resolver(self):
        """ERROR is treated the same as UNKNOWN — both mean the solver
        couldn't give a definitive answer. UNSAT is the only "give up"
        status."""
        from pyct.engine.engine import Engine

        plugin = _RecordingPlugin(resolution={"x": 55})
        engine, dispatcher, state, signature = _build_engine_with_queue(
            [(None, "error")],
            plugin,
        )
        engine.constraints_to_solve = ["(> x_VAR 0)"]

        result = Engine._next_input(
            engine,
            input_queue=[],
            initial_args={"x": 0},
            var_to_types={"x_VAR": "Int"},
            state=state,
            dispatcher=dispatcher,
            target=_simple_target,
            signature=signature,
        )

        assert plugin.unknown_calls == ["(> x_VAR 0)"]
        assert result == {"x": 55}


class TestNextInputBudgetCheck:
    """Budget enforcement inside _next_input.

    When the solver takes a long time per call, _next_input must check
    elapsed time between solver calls and bail out rather than burning
    the remaining budget on constraints that won't matter.
    """

    def test_terminates_when_budget_exceeded_between_solver_calls(self):
        """Given 2 constraints queued, budget already expired after first
        solver call, _next_input should terminate and return None rather
        than processing the second constraint."""
        import time

        from pyct.config.execution import ExecutionConfig
        from pyct.engine.engine import Engine

        plugin = _RecordingPlugin()
        engine, dispatcher, state, signature = _build_engine_with_queue(
            [(None, "unsat"), ({"x": 5}, "sat")],
            plugin,
        )
        engine.constraints_to_solve = ["constraint_1", "constraint_2"]

        # Budget is 1s but 100s have already elapsed
        engine.config = ExecutionConfig(timeout_seconds=1.0)
        state.start_time = time.monotonic() - 100

        result = Engine._next_input(
            engine,
            input_queue=[],
            initial_args={"x": 0},
            var_to_types={"x_VAR": "Int"},
            state=state,
            dispatcher=dispatcher,
            target=_simple_target,
            signature=signature,
        )

        assert result is None
        assert state.terminated is True
        assert state.termination_reason == "timeout"
        # Only first constraint should have been sent to solver
        assert len(engine.solver.calls) == 1

    def test_does_not_terminate_when_budget_has_remaining_time(self):
        """When budget is ample, _next_input processes all constraints
        normally and returns a solved input."""
        from pyct.engine.engine import Engine

        plugin = _RecordingPlugin()
        engine, dispatcher, state, signature = _build_engine_with_queue(
            [(None, "unsat"), ({"x": 5}, "sat")],
            plugin,
        )
        engine.constraints_to_solve = ["constraint_1", "constraint_2"]

        result = Engine._next_input(
            engine,
            input_queue=[],
            initial_args={"x": 0},
            var_to_types={"x_VAR": "Int"},
            state=state,
            dispatcher=dispatcher,
            target=_simple_target,
            signature=signature,
        )

        assert result == {"x": 5}
        assert state.terminated is False
        assert len(engine.solver.calls) == 2
