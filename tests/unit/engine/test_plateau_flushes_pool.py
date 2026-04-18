"""Plateau trigger clears the constraint pool before dispatching the
``on_coverage_plateau`` event.

Matches the paper's description in §3: "the engine enters the plateau
discovery path. It first flushes the constraint pool, since the existing
path constraints have produced no coverage improvement for tau
consecutive iterations." Legacy implements this via
``_clear_stale_constraints()`` inside ``_try_stale_candidates``.

Seed-phase plateaus stay suppressed so that pre-queued seeds can drain
without triggering LLM recovery.
"""

from __future__ import annotations

import inspect
from typing import Any

from pyct.config.execution import ExecutionConfig
from pyct.engine.engine import Engine
from pyct.engine.plugin.dispatcher import Dispatcher
from pyct.engine.state import ExplorationState


class _PlateauPlugin:
    name = "plateau_plugin"
    priority = 100

    def __init__(self, seeds: list[dict[str, Any]] | None = None):
        self.seeds = seeds or []
        self.calls = 0

    def on_coverage_plateau(self, ctx: Any) -> list[dict[str, Any]]:
        self.calls += 1
        return list(self.seeds)


def _target(x: int) -> int:
    return x


def _build_dispatcher(engine: Engine) -> Dispatcher:
    return Dispatcher(engine.plugins)


def test_plateau_flushes_constraint_pool() -> None:
    """When plateau fires, pre-existing path constraints are cleared."""
    config = ExecutionConfig(max_iterations=10, plateau_threshold=2)
    engine = Engine(config)
    plugin = _PlateauPlugin(seeds=[{"x": 1}])
    engine.register(plugin)
    engine.constraints_to_solve.extend([object(), object()])

    state = ExplorationState(seed_phase=False)
    engine._handle_plateau(
        state=state,
        last_coverage_size=0,
        stale_count=config.plateau_threshold,
        input_queue=[],
        dispatcher=_build_dispatcher(engine),
        target=_target,
        signature=inspect.signature(_target),
    )

    assert engine.constraints_to_solve == [], (
        "plateau trigger must flush the constraint pool; "
        f"leftover entries: {engine.constraints_to_solve}"
    )
    assert plugin.calls == 1, "on_coverage_plateau should fire exactly once"


def test_plateau_suppressed_during_seed_phase() -> None:
    """Plateau dispatch is suppressed while pre-queued seeds remain."""
    config = ExecutionConfig(max_iterations=10, plateau_threshold=2)
    engine = Engine(config)
    plugin = _PlateauPlugin(seeds=[{"x": 1}])
    engine.register(plugin)

    state = ExplorationState(seed_phase=True)
    engine._handle_plateau(
        state=state,
        last_coverage_size=0,
        stale_count=config.plateau_threshold,
        input_queue=[{"x": 2}],
        dispatcher=_build_dispatcher(engine),
        target=_target,
        signature=inspect.signature(_target),
    )

    assert plugin.calls == 0, "plateau must not fire during seed phase"
