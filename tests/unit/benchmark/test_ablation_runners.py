"""Single-component ablation runners isolate one LLM integration point.

Each runner restricts the LLM to one of the paper's three integration
points, measured against the bare-concolic baseline:

- ``seeds_only``: engine seeded by the LLM seed set, no in-loop LLM.
- ``plateau_only``: bare engine + the LLM plateau-discovery trigger.
- ``solver_fail_only``: bare engine + the LLM solver-failure trigger.

The seed component is controlled by whether ``seed_inputs`` carries the
LLM seeds (the engine bypasses ``on_seed_request`` when seeds are
supplied); the in-loop components are controlled by the plugin's
``enabled_points``. These tests dispatch through ``_run_single`` so they
exercise the name routing and the engine wiring together, with
``run_concolic`` stubbed to capture what each runner asks the engine to do.
"""

from __future__ import annotations

import pytest
from tools.benchmark.models import BenchmarkConfig
from tools.benchmark.runners import (
    CONCOLIC_LLM,
    PLATEAU_ONLY,
    PURE_CONCOLIC,
    SEEDS_ONLY,
    SOLVER_FAIL_ONLY,
)
from tools.benchmark.suite import SEED_RUNNERS, _run_single
from tools.benchmark.targets import BenchmarkTarget

from pyct.engine.result import RunConcolicResult
from pyct.plugins.llm import LLMPoint

_SEEDS = [{"x": 1, "y": 2}, {"x": 3, "y": 4}]


@pytest.fixture
def target() -> BenchmarkTarget:
    return BenchmarkTarget(
        name="classify",
        module="tests.unit.benchmark._fixtures.branching_target",
        function="classify",
        initial_args={"x": 0, "y": 0},
    )


@pytest.fixture
def config() -> BenchmarkConfig:
    return BenchmarkConfig()


class _StubClient:
    def get_stats(self) -> dict[str, int]:
        return {"input_tokens": 0, "output_tokens": 0}


def _capture(monkeypatch) -> dict:
    """Stub run_concolic to record (seed_inputs, plugins); stub the client."""
    captured: dict = {}

    def fake_run_concolic(func, args, *, config, isolated, seed_inputs=None, plugins=None):  # noqa: ARG001
        captured["seed_inputs"] = seed_inputs
        captured["plugins"] = plugins
        return RunConcolicResult(
            success=True,
            coverage_percent=0.0,
            executed_lines=frozenset(),
            paths_explored=0,
            inputs_generated=(),
            iterations=0,
            termination_reason="exhausted",
        )

    monkeypatch.setattr("pyct.run_concolic", fake_run_concolic)
    monkeypatch.setattr(
        "pyct.plugins.llm.client.build_default_client", lambda: _StubClient()
    )
    return captured


def _enabled_points(captured) -> frozenset:
    plugins = captured["plugins"]
    assert len(plugins) == 1, f"expected exactly one plugin, got {plugins!r}"
    return plugins[0]._enabled_points


class TestAblationWiring:
    def test_seeds_only_passes_seeds_and_no_inloop_plugin(self, target, config, monkeypatch):
        captured = _capture(monkeypatch)

        _run_single(target, SEEDS_ONLY, config, _SEEDS, seed_time=0.0)

        assert captured["seed_inputs"] == _SEEDS
        assert captured["plugins"] == []

    def test_plateau_only_drops_seeds_enables_plateau_point(self, target, config, monkeypatch):
        captured = _capture(monkeypatch)

        _run_single(target, PLATEAU_ONLY, config, _SEEDS, seed_time=0.0)

        assert captured["seed_inputs"] == []
        assert _enabled_points(captured) == frozenset({LLMPoint.PLATEAU})

    def test_solver_fail_only_drops_seeds_enables_solver_point(
        self, target, config, monkeypatch
    ):
        captured = _capture(monkeypatch)

        _run_single(target, SOLVER_FAIL_ONLY, config, _SEEDS, seed_time=0.0)

        assert captured["seed_inputs"] == []
        assert _enabled_points(captured) == frozenset({LLMPoint.SOLVER_FAILURE})

    def test_full_runner_keeps_seeds_and_all_points(self, target, config, monkeypatch):
        """Regression guard: refactoring run_concolic_llm must not change it."""
        captured = _capture(monkeypatch)

        _run_single(target, CONCOLIC_LLM, config, _SEEDS, seed_time=0.0)

        assert captured["seed_inputs"] == _SEEDS
        assert _enabled_points(captured) == frozenset(LLMPoint)


class TestSeedConsumingSet:
    def test_seeds_only_consumes_shared_seeds(self):
        assert SEEDS_ONLY in SEED_RUNNERS

    def test_inloop_ablations_do_not_consume_seeds(self):
        assert PLATEAU_ONLY not in SEED_RUNNERS
        assert SOLVER_FAIL_ONLY not in SEED_RUNNERS


class TestCliAliases:
    def test_single_on_aliases_resolve(self):
        from tools.benchmark.cli import _resolve_runners

        assert _resolve_runners(["so", "po", "fo"]) == [
            SEEDS_ONLY,
            PLATEAU_ONLY,
            SOLVER_FAIL_ONLY,
        ]

    def test_ablation_group_expands_to_baseline_singles_and_full(self):
        from tools.benchmark.cli import _resolve_runners

        assert _resolve_runners(["ablation"]) == [
            PURE_CONCOLIC,
            SEEDS_ONLY,
            PLATEAU_ONLY,
            SOLVER_FAIL_ONLY,
            CONCOLIC_LLM,
        ]
