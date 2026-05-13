"""Tests for Engine wiring of contract discovery (ST-Lane2)."""

from __future__ import annotations

from typing import Any

import icontract

from pyct.config.execution import ExecutionConfig
from pyct.contracts import EMPTY_CONTRACTS, ContractSet
from pyct.engine.engine import Engine


def test_engine_init_has_empty_contracts() -> None:
    engine = Engine(ExecutionConfig())
    assert engine.contracts is EMPTY_CONTRACTS


class _ContractsCapturePlugin:
    name = "contracts-capture"
    priority = 0

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self.captured: ContractSet | None = None

    def on_exploration_start(self, ctx: Any) -> None:
        del ctx
        self.captured = self._engine.contracts


def test_engine_contracts_populated_before_on_exploration_start() -> None:
    engine = Engine(ExecutionConfig(max_iterations=1, timeout_seconds=5.0))
    plugin = _ContractsCapturePlugin(engine)
    engine.register(plugin)

    @icontract.require(lambda x: x > 0, description="positive")
    def target(x: int) -> int:
        return x

    engine.explore(target, {"x": 1})

    assert plugin.captured is not None
    assert len(plugin.captured.requires) == 1
    assert plugin.captured.requires[0].description == "positive"


def test_engine_contracts_reset_after_explore() -> None:
    engine = Engine(ExecutionConfig(max_iterations=1, timeout_seconds=5.0))

    @icontract.require(lambda x: x > 0)
    def target(x: int) -> int:
        return x

    engine.explore(target, {"x": 1})
    assert engine.contracts is EMPTY_CONTRACTS
