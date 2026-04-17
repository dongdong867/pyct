"""``run_concolic_llm`` unions plain-seed coverage with engine coverage.

When the engine subprocess is killed by the watchdog or terminates early
before replaying all LLM seeds, ``result.inputs_generated`` and
``result.executed_lines`` can be empty or partial. A plain replay of the
original seeds must still contribute coverage so the invariant
``concolic_llm >= llm_only`` holds regardless of engine outcome.
"""

from __future__ import annotations

from typing import Any

import pytest
from tools.benchmark.models import BenchmarkConfig
from tools.benchmark.runners import run_concolic_llm
from tools.benchmark.targets import BenchmarkTarget

from pyct.engine.result import RunConcolicResult


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


def _empty_engine_result() -> RunConcolicResult:
    """What ``run_concolic`` returns on watchdog kill or early crash."""
    return RunConcolicResult(
        success=False,
        coverage_percent=0.0,
        executed_lines=frozenset(),
        paths_explored=0,
        inputs_generated=(),
        iterations=0,
        termination_reason="error",
        error="child exceeded wall-clock timeout of 110.0s",
    )


def _patch_llm_client(monkeypatch) -> None:
    """Fake an LLM client so the LLMPlugin registers — plugin state is
    irrelevant here since we stub ``run_concolic`` itself.
    """

    class _StubClient:
        def get_stats(self) -> dict[str, int]:
            return {"input_tokens": 0, "output_tokens": 0}

    monkeypatch.setattr(
        "pyct.plugins.llm.client.build_default_client",
        lambda: _StubClient(),
    )


def _capture_run_concolic(monkeypatch, response: RunConcolicResult) -> list[dict[str, Any]]:
    """Stub ``pyct.run_concolic`` to return ``response``; record seed_inputs."""
    captured: list[dict[str, Any]] = []

    def fake_run_concolic(func, args, *, config, isolated, seed_inputs, plugins):
        captured.extend(seed_inputs or [])
        return response

    monkeypatch.setattr("pyct.run_concolic", fake_run_concolic)
    return captured


def test_union_covers_seed_lines_when_engine_returns_empty(monkeypatch, target, config):
    """Engine killed by watchdog → empty result. Plain seed replay must
    still contribute coverage so the final RunnerResult reflects what
    ``llm_only`` alone would have produced.
    """
    _patch_llm_client(monkeypatch)
    _capture_run_concolic(monkeypatch, _empty_engine_result())

    seeds = [
        {"x": 5, "y": 0},  # covers: if x>0 body → return 1
        {"x": 0, "y": 5},  # covers: if x>0 false, if y>0 true → return 2
        {"x": -1, "y": -1},  # covers: both false → return 0
    ]

    result = run_concolic_llm(target, config, seeds, seed_time=0.0)

    # Plain-replay of these three seeds covers every branch of classify()
    # (def line + 5 body lines). Without the union this would be 0%.
    assert result.coverage is not None, "coverage missing when engine returned empty"
    assert result.coverage.executed_lines >= 5, (
        f"expected plain-seed replay to recover >=5 lines, got {result.coverage.executed_lines}"
    )
    assert result.coverage.coverage_percent >= 80.0


def test_union_preserves_engine_lines_when_engine_adds_coverage(monkeypatch, target, config):
    """Engine covers line 9 (the first ``if``); seeds cover lines 11-13.
    Union must expose both.
    """
    _patch_llm_client(monkeypatch)
    engine_only = RunConcolicResult(
        success=True,
        coverage_percent=20.0,
        executed_lines=frozenset({9, 10}),
        paths_explored=1,
        inputs_generated=({"x": 1, "y": 0},),
        iterations=1,
        termination_reason="exhausted",
    )
    _capture_run_concolic(monkeypatch, engine_only)

    seeds = [{"x": 0, "y": 5}, {"x": -1, "y": -1}]

    result = run_concolic_llm(target, config, seeds, seed_time=0.0)

    # Engine covered lines 9+10, seeds cover 11+12+13. Union = 5 body lines
    # + def line via backfill = 6 out of 6.
    assert result.coverage.executed_lines == 6
    assert result.coverage.coverage_percent == 100.0


def test_seeds_are_passed_to_engine(monkeypatch, target, config):
    """Sanity check: the union logic must not skip passing seeds to the
    engine — they're still the primary driver of concolic_llm's value.
    """
    _patch_llm_client(monkeypatch)
    captured = _capture_run_concolic(monkeypatch, _empty_engine_result())

    seeds = [{"x": 1, "y": 0}, {"x": 0, "y": 1}]
    run_concolic_llm(target, config, seeds, seed_time=0.0)

    assert captured == seeds
