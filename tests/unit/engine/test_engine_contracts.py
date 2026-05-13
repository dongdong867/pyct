"""Tests for Engine wiring of contract discovery (ST-Lane2)."""

from __future__ import annotations

from typing import Any

import icontract
import pytest

from pyct.config.execution import ExecutionConfig
from pyct.contracts import EMPTY_CONTRACTS, ContractSet
from pyct.engine import engine as engine_module
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


def test_engine_context_default_contracts_is_empty() -> None:
    from pyct.engine.plugin.context import EngineContext

    fields_default = EngineContext.__dataclass_fields__["contracts"].default
    assert fields_default is EMPTY_CONTRACTS


class _ContextContractsCapturePlugin:
    name = "ctx-contracts-capture"
    priority = 0

    def __init__(self) -> None:
        self.captured: ContractSet | None = None

    def on_exploration_start(self, ctx: Any) -> None:
        self.captured = ctx.contracts


def test_engine_context_threads_contracts_to_plugin() -> None:
    engine = Engine(ExecutionConfig(max_iterations=1, timeout_seconds=5.0))
    plugin = _ContextContractsCapturePlugin()
    engine.register(plugin)

    @icontract.require(lambda x: x > 0, description="ctx-positive")
    def target(x: int) -> int:
        return x

    engine.explore(target, {"x": 1})

    assert plugin.captured is not None
    assert len(plugin.captured.requires) == 1
    assert plugin.captured.requires[0].description == "ctx-positive"


def test_exploration_result_default_contracts_is_empty() -> None:
    from pyct.engine.result import ExplorationResult

    fields_default = ExplorationResult.__dataclass_fields__["contracts"].default
    assert fields_default is EMPTY_CONTRACTS


def test_explore_result_carries_discovered_contracts() -> None:
    engine = Engine(ExecutionConfig(max_iterations=1, timeout_seconds=5.0))

    @icontract.require(lambda x: x > 0, description="result-positive")
    @icontract.ensure(lambda result: result >= 0, description="result-non-neg")
    def target(x: int) -> int:
        return x

    result = engine.explore(target, {"x": 1})
    assert len(result.contracts.requires) == 1
    assert result.contracts.requires[0].description == "result-positive"
    assert len(result.contracts.ensures) == 1
    assert result.contracts.ensures[0].description == "result-non-neg"


def test_discover_contracts_runs_before_try_rewrite(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    call_order: list[str] = []
    real_discover = engine_module.discover_contracts
    real_rewrite = engine_module._try_rewrite

    def spy_discover(target: Any) -> Any:
        call_order.append("discover")
        return real_discover(target)

    def spy_rewrite(target: Any) -> Any:
        call_order.append("rewrite")
        return real_rewrite(target)

    monkeypatch.setattr(engine_module, "discover_contracts", spy_discover)
    monkeypatch.setattr(engine_module, "_try_rewrite", spy_rewrite)

    @icontract.require(lambda x: x > 0)
    def target(x: int) -> int:
        return x

    engine = Engine(ExecutionConfig(max_iterations=1, timeout_seconds=5.0))
    engine.explore(target, {"x": 1})

    assert "discover" in call_order
    assert "rewrite" in call_order
    assert call_order.index("discover") < call_order.index("rewrite")
