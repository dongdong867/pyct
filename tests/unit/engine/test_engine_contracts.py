"""Unit tests for Engine contracts lifecycle wiring + threading."""

from __future__ import annotations

from pyct.config.execution import ExecutionConfig
from pyct.engine.engine import Engine


def _sample_target(x: int) -> int:
    if x > 0:
        return 1
    return 0


class _ContextSpy:
    """Plugin capturing EngineContext snapshots passed to event handlers."""

    name = "context-spy"
    priority = 100

    def __init__(self):
        self.snapshots: list = []

    def on_exploration_start(self, ctx):
        self.snapshots.append(ctx)


def _attach_marker_contracts(target):
    """Attach a non-empty ContractSet marker to ``target`` for identity tests."""
    from pyct.contracts import Contract, ContractSet

    marker = ContractSet(
        requires=(
            Contract(
                predicate=lambda x: True,
                description="marker",
                source="<marker>:0",
                condition_args=("x",),
            ),
        )
    )
    target.__pyct_contracts__ = marker
    return marker


class TestEngineContractsInit:
    def test_engine_contracts_attr_initially_empty(self):
        from pyct.contracts import EMPTY_CONTRACTS

        engine = Engine(ExecutionConfig())
        assert engine.contracts is EMPTY_CONTRACTS


class TestEngineContractsLifecycle:
    def test_populates_contracts_before_plugin_dispatch_undecorated(self):
        from pyct.contracts import EMPTY_CONTRACTS

        spy = _ContextSpy()
        engine = Engine(ExecutionConfig(max_iterations=2, timeout_seconds=5.0))
        engine.explore(_sample_target, {"x": 0}, plugins=[spy])

        assert spy.snapshots, "spy should observe on_exploration_start"
        assert spy.snapshots[0].contracts is EMPTY_CONTRACTS

    def test_populates_contracts_before_plugin_dispatch_decorated(self):
        def target(x):
            return x

        marker = _attach_marker_contracts(target)

        spy = _ContextSpy()
        engine = Engine(ExecutionConfig(max_iterations=2, timeout_seconds=5.0))
        engine.explore(target, {"x": 0}, plugins=[spy])

        assert spy.snapshots
        assert spy.snapshots[0].contracts is marker

    def test_resets_contracts_to_empty_after_explore(self):
        from pyct.contracts import EMPTY_CONTRACTS

        def target(x):
            return x

        _attach_marker_contracts(target)
        engine = Engine(ExecutionConfig(max_iterations=1, timeout_seconds=5.0))
        engine.explore(target, {"x": 0})

        assert engine.contracts is EMPTY_CONTRACTS

    def test_consecutive_explores_isolated(self):
        def t_a(x):
            return x

        def t_b(x):
            return x

        marker_a = _attach_marker_contracts(t_a)
        marker_b = _attach_marker_contracts(t_b)

        spy = _ContextSpy()
        engine = Engine(ExecutionConfig(max_iterations=1, timeout_seconds=5.0))
        engine.explore(t_a, {"x": 0}, plugins=[spy])
        engine.explore(t_b, {"x": 0}, plugins=[spy])

        assert spy.snapshots[0].contracts is marker_a
        assert spy.snapshots[1].contracts is marker_b

    def test_populates_pre_rewrite_target_identity(self):
        """Discovery anchors on the original target, not the rewritten copy."""

        def target(x):
            if x > 0:
                return 1
            return 0

        marker = _attach_marker_contracts(target)

        spy = _ContextSpy()
        engine = Engine(ExecutionConfig(max_iterations=2, timeout_seconds=5.0))
        engine.explore(target, {"x": 0}, plugins=[spy])

        assert spy.snapshots[0].contracts is marker


class TestEngineContractsResult:
    def test_exploration_result_carries_contracts(self):
        def target(x):
            return x

        marker = _attach_marker_contracts(target)
        engine = Engine(ExecutionConfig(max_iterations=1, timeout_seconds=5.0))
        result = engine.explore(target, {"x": 0})

        assert result.contracts is marker

    def test_exploration_result_empty_for_undecorated(self):
        from pyct.contracts import EMPTY_CONTRACTS

        engine = Engine(ExecutionConfig(max_iterations=1, timeout_seconds=5.0))
        result = engine.explore(_sample_target, {"x": 0})

        assert result.contracts is EMPTY_CONTRACTS


class TestEngineContractsFiltering:
    def test_engine_filters_violating_precondition_input(self):
        from pyct.contracts import Contract, ContractSet

        def target(x: int) -> int:
            if x > 0:
                return 1
            return 0

        target.__pyct_contracts__ = ContractSet(
            requires=(
                Contract(
                    predicate=lambda x: x > 0,
                    description="x > 0",
                    source="<t>:1",
                    condition_args=("x",),
                ),
            )
        )

        engine = Engine(ExecutionConfig(max_iterations=20, timeout_seconds=10.0))
        result = engine.explore(target, {"x": -1})

        violating = [r for r in result.inputs_generated if r.args.get("x", 1) <= 0]
        assert violating == [], (
            f"violating x<=0 candidates must be filtered from inputs_generated; "
            f"got {result.inputs_generated}"
        )
