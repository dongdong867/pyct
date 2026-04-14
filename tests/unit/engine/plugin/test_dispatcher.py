"""Unit tests for plugin event Dispatcher."""

from pyct.engine.plugin.dispatcher import Dispatcher


class _FakeContext:
    """Minimal fake context for dispatcher tests that don't exercise context fields."""


class _RecordingPlugin:
    """Test helper that records calls and returns a configurable value."""

    def __init__(self, name: str, priority: int = 100, return_value=None):
        self.name = name
        self.priority = priority
        self._return = return_value
        self.calls: list[tuple[str, tuple]] = []

    def on_exploration_start(self, ctx):
        self.calls.append(("on_exploration_start", (ctx,)))

    def on_exploration_end(self, ctx, result):
        self.calls.append(("on_exploration_end", (ctx, result)))

    def on_seed_request(self, ctx):
        self.calls.append(("on_seed_request", (ctx,)))
        return self._return if self._return is not None else []

    def on_coverage_plateau(self, ctx):
        self.calls.append(("on_coverage_plateau", (ctx,)))
        return self._return if self._return is not None else []

    def on_constraint_unknown(self, ctx, constraint):
        self.calls.append(("on_constraint_unknown", (ctx, constraint)))
        return self._return


class TestObserverDispatch:
    def test_observer_calls_every_registered_plugin(self):
        p1 = _RecordingPlugin("p1")
        p2 = _RecordingPlugin("p2")
        dispatcher = Dispatcher([p1, p2])

        ctx = _FakeContext()
        dispatcher.dispatch_observer("on_exploration_start", ctx)

        assert len(p1.calls) == 1
        assert len(p2.calls) == 1

    def test_observer_skips_plugin_without_event_handler(self):
        class PartialPlugin:
            name = "partial"
            priority = 100
            # no on_exploration_start handler

        dispatcher = Dispatcher([PartialPlugin()])
        ctx = _FakeContext()

        # Should not raise AttributeError
        dispatcher.dispatch_observer("on_exploration_start", ctx)

    def test_observer_passes_extra_args(self):
        p1 = _RecordingPlugin("p1")
        dispatcher = Dispatcher([p1])

        ctx = _FakeContext()
        fake_result = object()
        dispatcher.dispatch_observer("on_exploration_end", ctx, fake_result)

        assert p1.calls == [("on_exploration_end", (ctx, fake_result))]


class TestCollectorDispatch:
    def test_collector_concatenates_results_from_all_plugins(self):
        p1 = _RecordingPlugin("p1", return_value=[{"x": 1}])
        p2 = _RecordingPlugin("p2", return_value=[{"x": 2}, {"x": 3}])
        dispatcher = Dispatcher([p1, p2])

        ctx = _FakeContext()
        results = dispatcher.dispatch_collector("on_seed_request", ctx)

        assert results == [{"x": 1}, {"x": 2}, {"x": 3}]

    def test_collector_filters_empty_results(self):
        p1 = _RecordingPlugin("p1", return_value=[])
        p2 = _RecordingPlugin("p2", return_value=[{"x": 1}])
        dispatcher = Dispatcher([p1, p2])

        ctx = _FakeContext()
        results = dispatcher.dispatch_collector("on_seed_request", ctx)

        assert results == [{"x": 1}]

    def test_collector_skips_plugin_without_event_handler(self):
        class PartialPlugin:
            name = "partial"
            priority = 100

        p = _RecordingPlugin("p", return_value=[{"x": 1}])
        dispatcher = Dispatcher([PartialPlugin(), p])

        ctx = _FakeContext()
        results = dispatcher.dispatch_collector("on_seed_request", ctx)

        assert results == [{"x": 1}]


class TestResolverDispatch:
    def test_resolver_returns_first_non_none_result(self):
        p1 = _RecordingPlugin("p1", return_value=None)
        p2 = _RecordingPlugin("p2", return_value={"x": 42})
        dispatcher = Dispatcher([p1, p2])

        ctx = _FakeContext()
        result = dispatcher.dispatch_resolver("on_constraint_unknown", ctx, "constraint")

        assert result == {"x": 42}

    def test_resolver_short_circuits_after_first_match(self):
        p1 = _RecordingPlugin("p1", priority=50, return_value={"x": 1})
        p2 = _RecordingPlugin("p2", priority=100, return_value={"x": 2})
        dispatcher = Dispatcher([p1, p2])

        ctx = _FakeContext()
        result = dispatcher.dispatch_resolver("on_constraint_unknown", ctx, "constraint")

        assert result == {"x": 1}
        assert len(p1.calls) == 1
        assert len(p2.calls) == 0  # short-circuited

    def test_resolver_returns_none_when_all_plugins_return_none(self):
        p1 = _RecordingPlugin("p1", return_value=None)
        p2 = _RecordingPlugin("p2", return_value=None)
        dispatcher = Dispatcher([p1, p2])

        ctx = _FakeContext()
        result = dispatcher.dispatch_resolver("on_constraint_unknown", ctx, "constraint")

        assert result is None


class TestPriorityOrdering:
    def test_lower_priority_runs_first(self):
        execution_order: list[str] = []

        class OrderedPlugin:
            def __init__(self, name: str, priority: int):
                self.name = name
                self.priority = priority

            def on_exploration_start(self, ctx):
                execution_order.append(self.name)

        # Register in reverse order to verify sort, not registration order
        p_high = OrderedPlugin("high", 200)
        p_mid = OrderedPlugin("mid", 100)
        p_low = OrderedPlugin("low", 50)

        dispatcher = Dispatcher([p_high, p_mid, p_low])
        dispatcher.dispatch_observer("on_exploration_start", _FakeContext())

        assert execution_order == ["low", "mid", "high"]


class TestDispatcherErrorHandling:
    """Error-path behavior: observer suppresses, collector/resolver propagate."""

    def test_observer_suppresses_plugin_exceptions(self):
        class ExplodingPlugin:
            name = "boom"
            priority = 100

            def on_exploration_start(self, ctx):
                raise RuntimeError("plugin blew up")

        good = _RecordingPlugin("good")
        dispatcher = Dispatcher([ExplodingPlugin(), good])

        # Should not raise — observer errors are logged and swallowed
        dispatcher.dispatch_observer("on_exploration_start", _FakeContext())

        # The good plugin still runs after the exploding one
        assert len(good.calls) == 1

    def test_observer_continues_after_plugin_exception(self):
        order: list[str] = []

        class ExplodingFirst:
            name = "boom"
            priority = 50

            def on_exploration_start(self, ctx):
                order.append("boom")
                raise RuntimeError("oops")

        class SecondPlugin:
            name = "second"
            priority = 100

            def on_exploration_start(self, ctx):
                order.append("second")

        dispatcher = Dispatcher([ExplodingFirst(), SecondPlugin()])
        dispatcher.dispatch_observer("on_exploration_start", _FakeContext())

        assert order == ["boom", "second"]

    def test_collector_propagates_plugin_exceptions(self):
        """Collector does not suppress — plugin bugs surface to the caller."""
        import pytest

        class ExplodingPlugin:
            name = "boom"
            priority = 100

            def on_seed_request(self, ctx):
                raise ValueError("seed generation failed")

        dispatcher = Dispatcher([ExplodingPlugin()])
        with pytest.raises(ValueError, match="seed generation failed"):
            dispatcher.dispatch_collector("on_seed_request", _FakeContext())

    def test_resolver_propagates_plugin_exceptions(self):
        """Resolver does not suppress — plugin bugs surface to the caller."""
        import pytest

        class ExplodingPlugin:
            name = "boom"
            priority = 100

            def on_constraint_unknown(self, ctx, constraint):
                raise RuntimeError("resolver failed")

        dispatcher = Dispatcher([ExplodingPlugin()])
        with pytest.raises(RuntimeError, match="resolver failed"):
            dispatcher.dispatch_resolver("on_constraint_unknown", _FakeContext(), "c")


class TestDispatcherEmptyPluginList:
    """Degenerate input: a dispatcher with zero plugins should be a no-op."""

    def test_observer_with_no_plugins_noop(self):
        dispatcher = Dispatcher([])
        # Should not raise
        dispatcher.dispatch_observer("on_exploration_start", _FakeContext())

    def test_collector_with_no_plugins_returns_empty_list(self):
        dispatcher = Dispatcher([])
        result = dispatcher.dispatch_collector("on_seed_request", _FakeContext())
        assert result == []

    def test_resolver_with_no_plugins_returns_none(self):
        dispatcher = Dispatcher([])
        result = dispatcher.dispatch_resolver("on_constraint_unknown", _FakeContext(), "c")
        assert result is None


class TestDispatcherInvalidPlugins:
    def test_plugin_missing_priority_raises_attribute_error_at_init(self):
        import pytest

        class NoPriority:
            name = "bad"
            # priority is missing

        with pytest.raises(AttributeError):
            Dispatcher([NoPriority()])
