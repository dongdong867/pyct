"""``iteration_start_callback`` fires before every ``_run_iteration``.

The isolated runner uses this callback to write ``iter_start`` tombstones
to its checkpoint pipe so the parent can reconstruct an in-flight
iteration as a TIMEOUT record on watchdog kill. The callback is engine
state — its contract is independent of the runner: it must fire for
every record-producing iteration the engine drives, including post-loop
discovery candidates and the post-loop solver mini-loop.
"""

from __future__ import annotations

from typing import Any

from pyct.config.execution import ExecutionConfig
from pyct.engine.engine import Engine
from pyct.engine.types import Provenance


def _branching(x: int) -> int:
    if x > 0:
        return 1
    return 0


def _gated_target(x: str) -> int:
    """Target with a regex gate the SMT solver can't reason about."""
    import re

    if re.match(r"^hello$", x):
        return 1
    return 0


class _PostLoopPlugin:
    name = "post_loop"
    priority = 100

    def __init__(self, candidates: list[dict[str, Any]]) -> None:
        self._candidates = candidates
        self.calls = 0

    def on_post_loop_discovery(self, ctx: Any) -> list[dict[str, Any]]:
        self.calls += 1
        if self.calls > 1:
            return []
        return [dict(c) for c in self._candidates]


class TestIterationStartCallbackFires:
    def test_fires_once_per_main_loop_iteration(self):
        """One call per record produced by the main loop."""
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        starts: list[tuple[dict, Provenance]] = []

        def on_start(eng, state, args, provenance):  # noqa: ARG001
            starts.append((dict(args), provenance))

        result = engine.explore(_branching, {"x": 0}, iteration_start_callback=on_start)

        assert len(starts) == result.iterations
        # The first start matches the initial seed before _run_iteration ran.
        assert starts[0] == ({"x": 0}, Provenance.SEED)

    def test_fires_with_solver_provenance_after_seed(self):
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        starts: list[Provenance] = []

        def on_start(eng, state, args, provenance):  # noqa: ARG001
            starts.append(provenance)

        engine.explore(_branching, {"x": 0}, iteration_start_callback=on_start)

        # Solver-flipped iterations must carry SOLVER provenance.
        assert Provenance.SOLVER in starts[1:]

    def test_fires_for_post_loop_candidates(self):
        config = ExecutionConfig(max_iterations=2, timeout_seconds=5.0, post_loop_rounds=1)
        engine = Engine(config)
        engine.register(_PostLoopPlugin(candidates=[{"x": "hello"}]))
        starts: list[tuple[dict, Provenance]] = []

        def on_start(eng, state, args, provenance):  # noqa: ARG001
            starts.append((dict(args), provenance))

        engine.explore(_gated_target, {"x": ""}, iteration_start_callback=on_start)

        # Post-loop candidate ran via _execute_post_loop_candidates and
        # must have fired the callback with PLUGIN_POST_LOOP provenance.
        assert ({"x": "hello"}, Provenance.PLUGIN_POST_LOOP) in starts

    def test_fires_before_run_iteration_so_args_match_record(self):
        """For every callback fired, the next record (if any) must carry
        the same args. This is what lets the runner build a tombstone:
        when the watchdog kills mid-iter, the args observed in iter_start
        equal the args that would have ended up on the dropped record.
        """
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        starts: list[dict] = []

        def on_start(eng, state, args, provenance):  # noqa: ARG001
            starts.append(dict(args))

        result = engine.explore(_branching, {"x": 0}, iteration_start_callback=on_start)

        record_args = [r.args for r in result.inputs_generated]
        assert starts == record_args


class TestIterationStartCallbackErrorContainment:
    def test_exception_in_callback_does_not_abort_run(self):
        """Engine swallows callback failures (parity with progress_callback)."""
        config = ExecutionConfig(max_iterations=5, timeout_seconds=5.0)
        engine = Engine(config)

        def on_start(eng, state, args, provenance):  # noqa: ARG001
            raise RuntimeError("simulated callback failure")

        result = engine.explore(_branching, {"x": 0}, iteration_start_callback=on_start)

        # Engine still produced records and a successful result.
        assert result.success is True
        assert len(result.inputs_generated) >= 1
