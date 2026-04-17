"""Seed-phase budget — seeds get their own budget, separate from exploration.

Regression guard for the ``concolic_llm`` "early termination" pathway.
Before the fix, ``max_iterations`` and ``timeout_seconds`` both counted
seed replay as exploration iterations. An LLM returning more seeds than
``max_iterations`` would silently drop the tail, and a wall-clock
timeout mid-seed left the rest unreplayed — producing a partial
``inputs_generated`` that the benchmark layer could not reassemble.
"""

from __future__ import annotations

from pyct.config.execution import ExecutionConfig
from pyct.engine.engine import Engine


def _branching(x: int) -> int:
    if x > 0:
        return 1
    return 0


def _three_path(x: int) -> str:
    """Target whose full coverage takes ``x > 1000`` — seeds alone won't satisfy it.

    Guards the test from the ``full_coverage`` termination blindspot,
    which would otherwise fire on the first positive seed and hide
    whether later seeds got a chance.
    """
    if x > 0:
        if x > 1000:
            return "big"
        return "pos"
    return "neg"


class TestSeedPhaseBudget:
    def test_all_seeds_run_when_count_exceeds_max_iterations(self):
        """Seeds beyond ``max_iterations`` must still be executed.

        With 1 initial arg + 5 seeds and ``max_iterations=2``, pre-fix
        the engine tried only the first 2 inputs. Post-fix all 6 run
        because seed replay is exempt from the iteration budget.
        """
        seeds = [{"x": i} for i in range(100, 105)]
        engine = Engine(ExecutionConfig(max_iterations=2, timeout_seconds=5.0))
        result = engine.explore(_three_path, {"x": 0}, seed_inputs=seeds)

        tried_xs = {a["x"] for a in result.inputs_generated}
        for seed in seeds:
            assert seed["x"] in tried_xs, f"missing seed {seed}"

    def test_exploration_iterations_still_bounded_by_max(self):
        """After seed phase, ``max_iterations`` still limits exploration."""

        def f(x: int) -> int:
            if x == 1:
                return 1
            if x == 2:
                return 2
            if x == 3:
                return 3
            return 0

        # 0 seeds → no seed phase → max_iterations=2 caps exploration.
        engine = Engine(ExecutionConfig(max_iterations=2, timeout_seconds=5.0))
        result = engine.explore(f, {"x": 0})
        assert len(result.inputs_generated) <= 2

    def test_seed_soft_timeout_applies_per_seed(self):
        """A hung seed must be cut at ``seed_soft_timeout``, not the global timeout.

        Global timeout is 10s; seed_soft_timeout is 1s. A busy-loop
        target would exceed both, but the per-seed soft-timeout catches
        it at ~1s per seed so remaining seeds still run.
        """

        def slow(x: int) -> int:
            if x == 999:
                import time

                time.sleep(3)
            if x > 0:
                return 1
            return 0

        engine = Engine(
            ExecutionConfig(
                max_iterations=5,
                timeout_seconds=10.0,
                seed_soft_timeout=1.0,
            )
        )
        result = engine.explore(
            slow,
            {"x": 0},
            seed_inputs=[{"x": 999}, {"x": 7}],
        )
        tried = {a["x"] for a in result.inputs_generated}
        assert 999 in tried
        assert 7 in tried
