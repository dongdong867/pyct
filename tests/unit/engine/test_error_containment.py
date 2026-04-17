"""Engine error-containment: wrap-time failures don't abort exploration.

Regression guard for the ``concolic_llm`` seed-0 crash pathway. Before
the fix, a ``wrap_arguments`` failure on any iteration escaped past
``_run_iteration`` → ``_exploration_loop`` → ``explore()`` and was
caught only by ``_child_entry``'s blanket ``except Exception``, nuking
the entire subprocess and abandoning every remaining seed.
"""

from __future__ import annotations

from pyct.config.execution import ExecutionConfig
from pyct.engine import engine as engine_module
from pyct.engine.engine import Engine


def _branching(x: int) -> int:
    if x > 0:
        return 1
    return 0


def _passthrough(x: int) -> int:
    return x


class TestWrapArgumentsFailureDoesNotAbort:
    def test_failing_wrap_on_first_seed_lets_remaining_seeds_run(self, monkeypatch):
        """One seed with failing wrap must not poison the other seeds.

        ``_branching`` has a partial-coverage initial arg so the engine
        does not short-circuit on ``full_coverage`` before later seeds
        get their turn.
        """
        original = engine_module.wrap_arguments
        wrap_attempts: list[dict] = []

        def flaky_wrap(args, engine):
            wrap_attempts.append(args)
            if args == {"x": 666}:
                raise AttributeError("simulated Concolic construction failure")
            return original(args, engine)

        monkeypatch.setattr(engine_module, "wrap_arguments", flaky_wrap)

        engine = Engine(ExecutionConfig(max_iterations=10, timeout_seconds=5.0))
        result = engine.explore(
            _branching,
            {"x": -5},
            seed_inputs=[{"x": 666}, {"x": 7}],
        )

        assert result.success is True
        tried_xs = {a["x"] for a in result.inputs_generated}
        assert 7 in tried_xs
        attempted_xs = [a["x"] for a in wrap_attempts]
        assert 666 in attempted_xs and 7 in attempted_xs

    def test_inputs_tried_records_failed_iteration(self, monkeypatch):
        """Arg that crashes during wrap must still show up in ``inputs_generated``.

        Otherwise the benchmark layer can't replay the seed to extract
        its plain-execution coverage, losing the llm_only fallback that
        ``_pyct_result_to_runner`` relies on.
        """
        original = engine_module.wrap_arguments
        raised = False

        def wrap_once(args, engine):
            nonlocal raised
            if not raised and args == {"x": 42}:
                raised = True
                raise AttributeError("first call fails")
            return original(args, engine)

        monkeypatch.setattr(engine_module, "wrap_arguments", wrap_once)

        engine = Engine(ExecutionConfig(max_iterations=5, timeout_seconds=5.0))
        result = engine.explore(_passthrough, {"x": 42})

        assert result.success is True
        assert any(a == {"x": 42} for a in result.inputs_generated)
