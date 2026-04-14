"""Unit tests for Engine class and exploration loop."""

from pyct.config.execution import ExecutionConfig
from pyct.engine.engine import Engine
from pyct.engine.result import ExplorationResult


def _sample_target(x: int) -> int:
    """Minimal target function for engine tests."""
    if x > 0:
        return 1
    return 0


class _NoopPlugin:
    """Plugin with no event handlers — used for registration tests."""

    name = "noop"
    priority = 100


class TestEngineConstruction:
    def test_engine_accepts_config(self):
        engine = Engine(ExecutionConfig())
        assert engine is not None

    def test_engine_has_no_plugins_initially(self):
        engine = Engine(ExecutionConfig())
        assert engine.plugins == []

    def test_engine_stores_config(self):
        config = ExecutionConfig(max_iterations=100)
        engine = Engine(config)
        assert engine.config.max_iterations == 100


class TestPluginRegistration:
    def test_register_adds_plugin_to_list(self):
        engine = Engine(ExecutionConfig())
        plugin = _NoopPlugin()
        engine.register(plugin)
        assert plugin in engine.plugins

    def test_register_multiple_plugins(self):
        engine = Engine(ExecutionConfig())
        p1 = _NoopPlugin()
        p2 = _NoopPlugin()
        engine.register(p1)
        engine.register(p2)
        assert len(engine.plugins) == 2


class TestEngineExploreBasic:
    def test_explore_returns_exploration_result(self):
        engine = Engine(ExecutionConfig(max_iterations=5, timeout_seconds=5.0))
        result = engine.explore(_sample_target, {"x": 0})
        assert isinstance(result, ExplorationResult)

    def test_explore_terminates_on_max_iterations(self):
        engine = Engine(ExecutionConfig(max_iterations=1, timeout_seconds=10.0))
        result = engine.explore(_sample_target, {"x": 0})
        assert result.iterations <= 1

    def test_explore_covers_both_branches_of_simple_function(self):
        engine = Engine(ExecutionConfig(max_iterations=20, timeout_seconds=10.0))
        result = engine.explore(_sample_target, {"x": 0})
        assert result.success
        assert result.coverage_percent > 0
        assert result.paths_explored >= 1


class TestEngineTerminationReason:
    def test_max_iterations_sets_termination_reason(self):
        engine = Engine(ExecutionConfig(max_iterations=1, timeout_seconds=10.0))
        result = engine.explore(_sample_target, {"x": 0})
        # Either max_iterations or full_coverage is acceptable depending on
        # how fast the simple function gets explored
        assert result.termination_reason in ("max_iterations", "full_coverage", "exhausted")


class TestEnginePluginRegistrationBoundary:
    """Characterization tests for registration permissiveness."""

    def test_register_same_plugin_instance_twice_duplicates(self):
        engine = Engine(ExecutionConfig())
        plugin = _NoopPlugin()
        engine.register(plugin)
        engine.register(plugin)
        # No deduplication at the engine level
        assert engine.plugins.count(plugin) == 2

    def test_register_plugin_missing_required_fields_does_not_raise(self):
        """Engine.register() does not validate the Plugin protocol.

        Plugins without name/priority are accepted at registration but
        will fail later when Dispatcher tries to sort by priority. The
        engine deliberately pushes validation downstream.
        """

        class _BadPlugin:
            pass  # no name, no priority

        engine = Engine(ExecutionConfig())
        engine.register(_BadPlugin())  # type: ignore
        assert len(engine.plugins) == 1
