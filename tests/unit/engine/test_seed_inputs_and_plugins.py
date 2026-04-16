"""Tests for seed_inputs and plugins parameters on Engine.explore,
run_concolic, and run_isolated.

seed_inputs: pre-generated input list prepended to the engine's input
queue. When provided, the engine skips its own on_seed_request dispatch
to avoid duplicating seeds.

plugins: list of Plugin instances registered on the engine before
exploration starts. For run_isolated, plugins are serialized through
the spawn boundary via pickle.
"""

from __future__ import annotations

from typing import Any

from pyct.config.execution import ExecutionConfig
from pyct.engine.engine import Engine


def _two_branch(x: int) -> int:
    if x > 10:
        return 1
    return 0


class _SeedRecorderPlugin:
    """Plugin that records on_seed_request calls and returns canned seeds."""

    name = "seed_recorder"
    priority = 100

    def __init__(self, seeds: list[dict[str, Any]] | None = None):
        self.seed_calls: int = 0
        self._seeds = seeds or []

    def on_seed_request(self, ctx: Any) -> list[dict[str, Any]]:
        self.seed_calls += 1
        return list(self._seeds)


class _PlateauRecorderPlugin:
    """Plugin that records on_coverage_plateau calls."""

    name = "plateau_recorder"
    priority = 100

    def __init__(self):
        self.plateau_calls: int = 0

    def on_coverage_plateau(self, ctx: Any) -> list[dict[str, Any]]:
        self.plateau_calls += 1
        return []


class TestEngineSeedInputs:
    def test_seed_inputs_are_explored_by_engine(self):
        """Pre-supplied seed inputs should be tried by the engine."""
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        result = engine.explore(
            _two_branch,
            {"x": 0},
            seed_inputs=[{"x": 20}],
        )
        # With x=0 (initial) and x=20 (seed), both branches should be hit
        assert result.coverage_percent == 100.0

    def test_seed_inputs_skip_on_seed_request_dispatch(self):
        """When seed_inputs is provided, on_seed_request should NOT fire."""
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        plugin = _SeedRecorderPlugin(seeds=[{"x": 99}])
        engine = Engine(config)
        engine.register(plugin)
        engine.explore(
            _two_branch,
            {"x": 0},
            seed_inputs=[{"x": 20}],
        )
        assert plugin.seed_calls == 0

    def test_without_seed_inputs_on_seed_request_fires_normally(self):
        """Without seed_inputs, on_seed_request dispatches as before."""
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        plugin = _SeedRecorderPlugin(seeds=[{"x": 20}])
        engine = Engine(config)
        engine.register(plugin)
        engine.explore(_two_branch, {"x": 0})
        assert plugin.seed_calls == 1

    def test_seed_inputs_empty_list_still_skips_on_seed_request(self):
        """An explicit empty list means 'no seeds' — different from None
        which means 'not provided, dispatch normally'."""
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        plugin = _SeedRecorderPlugin(seeds=[{"x": 20}])
        engine = Engine(config)
        engine.register(plugin)
        engine.explore(
            _two_branch,
            {"x": 0},
            seed_inputs=[],
        )
        assert plugin.seed_calls == 0


class TestEnginePluginsParam:
    def test_plugins_param_registers_before_explore(self):
        """Plugins passed via the plugins= param should be active during
        exploration — their on_seed_request fires."""
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        plugin = _SeedRecorderPlugin(seeds=[{"x": 20}])
        engine = Engine(config)
        engine.explore(
            _two_branch,
            {"x": 0},
            plugins=[plugin],
        )
        assert plugin.seed_calls == 1
        assert engine.plugins == [plugin]

    def test_plugins_param_combined_with_seed_inputs(self):
        """When both seed_inputs and plugins are provided, seeds are used
        but plugins are still registered for runtime events."""
        config = ExecutionConfig(
            max_iterations=5, timeout_seconds=5.0, plateau_threshold=2
        )
        seed_plugin = _SeedRecorderPlugin(seeds=[{"x": 99}])
        plateau_plugin = _PlateauRecorderPlugin()
        engine = Engine(config)
        engine.explore(
            _two_branch,
            {"x": 0},
            seed_inputs=[{"x": 20}],
            plugins=[seed_plugin, plateau_plugin],
        )
        # seed_inputs provided → on_seed_request skipped
        assert seed_plugin.seed_calls == 0
        # But plugin is registered and plateau may fire if stalled
        assert seed_plugin in engine.plugins
        assert plateau_plugin in engine.plugins


class TestRunConcolicSeedInputsAndPlugins:
    def test_run_concolic_in_process_with_seed_inputs(self):
        """run_concolic(isolated=False) should pass seed_inputs through."""
        from pyct import run_concolic

        result = run_concolic(
            _two_branch,
            {"x": 0},
            config=ExecutionConfig(max_iterations=10, timeout_seconds=5.0),
            isolated=False,
            seed_inputs=[{"x": 20}],
        )
        assert result.coverage_percent == 100.0

    def test_run_concolic_in_process_with_plugins(self):
        """run_concolic(isolated=False) should register plugins."""
        from pyct import run_concolic

        plugin = _SeedRecorderPlugin(seeds=[{"x": 20}])
        result = run_concolic(
            _two_branch,
            {"x": 0},
            config=ExecutionConfig(max_iterations=10, timeout_seconds=5.0),
            isolated=False,
            plugins=[plugin],
        )
        assert plugin.seed_calls == 1
        assert result.coverage_percent == 100.0

    def test_run_concolic_isolated_with_seed_inputs(self):
        """run_concolic(isolated=True) should pipe seed_inputs through
        the spawn boundary and use them in the child engine."""
        from pyct import run_concolic

        result = run_concolic(
            _two_branch,
            {"x": 0},
            config=ExecutionConfig(max_iterations=10, timeout_seconds=5.0),
            isolated=True,
            seed_inputs=[{"x": 20}],
        )
        assert result.coverage_percent == 100.0
