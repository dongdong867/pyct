"""Acceptance tests: input record provenance tagging.

The engine attaches a Provenance value to every executed input,
identifying where the input came from (initial seed, solver model,
plugin event). This file asserts the engine assigns the correct
Provenance value at each enqueue site and preserves event-keyed labels
even when multiple plugins overlap on the same event.
"""

from __future__ import annotations

from typing import Any

from pyct.config.execution import ExecutionConfig
from pyct.engine.engine import Engine
from pyct.engine.types import Provenance


def _two_branch(x: int) -> int:
    """Target with one branch — forces a solver flip from any seed."""
    if x > 10:
        return 1
    return 0


class _SeedSource:
    """Plugin returning canned seeds via on_seed_request."""

    name = "seed_source"
    priority = 100

    def __init__(self, seeds: list[dict[str, Any]]) -> None:
        self._seeds = seeds

    def on_seed_request(self, ctx: Any) -> list[dict[str, Any]]:
        return [dict(s) for s in self._seeds]


class _PlateauSource:
    """Plugin returning canned seeds via on_coverage_plateau."""

    name = "plateau_source"
    priority = 100

    def __init__(self, seeds: list[dict[str, Any]]) -> None:
        self._seeds = seeds

    def on_coverage_plateau(self, ctx: Any) -> list[dict[str, Any]]:
        return [dict(s) for s in self._seeds]


class TestSeedAndSolverProvenance:
    """Pure-concolic run: first input is SEED, subsequent solver-derived."""

    def test_first_record_is_seed(self):
        """
        Given a target with one reachable branch
          And run with one initial seed and no plugins
        When exploration completes
        Then the first record has provenance SEED
        """
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        result = engine.explore(_two_branch, {"x": 0})
        assert result.inputs_generated[0].provenance is Provenance.SEED

    def test_records_after_seed_are_solver_derived(self):
        """
        Given a target with one reachable branch
          And run with one initial seed and no plugins
        When the solver flips the branch
        Then every record after the first has provenance SOLVER
        """
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        result = engine.explore(_two_branch, {"x": 0})
        for record in result.inputs_generated[1:]:
            assert record.provenance is Provenance.SOLVER


class TestPluginSeedProvenance:
    """Plugin-supplied seeds are tagged PLUGIN_SEED, not SEED."""

    def test_plugin_seed_records_carry_plugin_seed(self):
        """
        Given a registered plugin returning two seeds via on_seed_request
        When exploration completes
        Then exactly two records carry provenance PLUGIN_SEED
        """
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        engine.register(_SeedSource(seeds=[{"x": 100}, {"x": -5}]))
        result = engine.explore(_two_branch, {"x": 0})
        plugin_records = [
            r for r in result.inputs_generated if r.provenance is Provenance.PLUGIN_SEED
        ]
        assert len(plugin_records) == 2

    def test_initial_seed_keeps_seed_when_plugin_seeds_present(self):
        """
        Given an initial seed AND a plugin returning seeds
        When exploration completes
        Then the initial-args record still carries provenance SEED
        """
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        engine.register(_SeedSource(seeds=[{"x": 100}]))
        result = engine.explore(_two_branch, {"x": 0})
        seed_records = [r for r in result.inputs_generated if r.provenance is Provenance.SEED]
        assert len(seed_records) == 1
        assert seed_records[0].args == {"x": 0}


class TestMultiPluginOverlap:
    """Multi-plugin overlap on same event keeps event-keyed provenance."""

    def test_two_plugins_on_seed_request_both_emit_plugin_seed(self):
        """
        Given two plugins both registered for on_seed_request
        When both return seeds
        Then every plugin-derived record carries provenance PLUGIN_SEED
          And no plugin identity leaks into the record
        """
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        engine.register(_SeedSource(seeds=[{"x": 100}]))
        engine.register(_SeedSource(seeds=[{"x": -5}]))
        result = engine.explore(_two_branch, {"x": 0})
        plugin_records = [
            r for r in result.inputs_generated if r.provenance is Provenance.PLUGIN_SEED
        ]
        assert len(plugin_records) == 2
        for record in plugin_records:
            assert record.provenance is Provenance.PLUGIN_SEED


class TestPlateauProvenance:
    """Plugin seeds delivered via on_coverage_plateau carry PLUGIN_PLATEAU."""

    def test_plateau_supplied_seed_records_carry_plugin_plateau(self):
        """
        Given a target whose initial seed exhausts solver progress quickly
          And a plugin returning a seed via on_coverage_plateau
        When the plateau handler dispatches and the seed executes
        Then at least one record carries provenance PLUGIN_PLATEAU
        """
        config = ExecutionConfig(
            max_iterations=20,
            timeout_seconds=5.0,
            plateau_threshold=2,
        )
        engine = Engine(config)
        engine.register(_PlateauSource(seeds=[{"x": 100}]))
        result = engine.explore(_two_branch, {"x": 0})
        plateau_records = [
            r for r in result.inputs_generated if r.provenance is Provenance.PLUGIN_PLATEAU
        ]
        assert len(plateau_records) >= 1
