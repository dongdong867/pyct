"""Unit tests for Plugin Protocol."""

from pyct.engine.plugin.protocol import Plugin


class TestPluginProtocol:
    def test_plugin_with_name_and_priority_satisfies_protocol(self):
        class ValidPlugin:
            name = "test"
            priority = 100

        assert isinstance(ValidPlugin(), Plugin)

    def test_plugin_without_name_fails_protocol_check(self):
        class InvalidPlugin:
            priority = 100

        assert not isinstance(InvalidPlugin(), Plugin)

    def test_plugin_without_priority_fails_protocol_check(self):
        class InvalidPlugin:
            name = "test"

        assert not isinstance(InvalidPlugin(), Plugin)

    def test_plugin_with_all_event_handlers_satisfies_protocol(self):
        class FullPlugin:
            name = "full"
            priority = 50

            def on_exploration_start(self, ctx):
                pass

            def on_exploration_end(self, ctx, result):
                pass

            def on_seed_request(self, ctx):
                return []

            def on_coverage_plateau(self, ctx):
                return []

            def on_constraint_unknown(self, ctx, constraint):
                return None

        assert isinstance(FullPlugin(), Plugin)

    def test_plugin_with_partial_event_handlers_still_satisfies_protocol(self):
        """Plugins only need to implement events they care about."""

        class PartialPlugin:
            name = "partial"
            priority = 100

            def on_seed_request(self, ctx):
                return [{"x": 1}]

        assert isinstance(PartialPlugin(), Plugin)
