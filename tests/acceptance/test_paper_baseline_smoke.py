"""Smoke gate for the paper baseline targets.

Cross-validates the full per-input telemetry pipeline end-to-end on
the six targets the paper reports: bmi/triangle/tax/log/url/email.
Each runs through ``run_concolic`` (pure mode — no LLM, no API cost),
hits ``_pyct_result_to_runner``, lands on ``RunnerResult``, and
serializes through ``save_results_json``. The assertions are
deliberately broad: this is a no-regression smoke gate, not a coverage
benchmark. Byte-for-byte comparison against the legacy
``run_20260327_030025`` numbers stays as a human gate post-merge —
those numbers depend on LLM-generated seeds we can't drive
deterministically from CI.

The gate proves three things:
1. ``run_concolic`` doesn't crash on any of the six paper targets.
2. ``RunnerResult`` carries records and counters in the schema the
   per-input telemetry sub-tasks added.
3. ``save_results_json`` round-trips the full payload — including any
   non-serializable values that might sneak through — without raising.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tools.benchmark.models import BenchmarkConfig, RunnerResult
from tools.benchmark.output import save_results_json
from tools.benchmark.runners import _pyct_result_to_runner
from tools.benchmark.targets import TEST_SUITE, BenchmarkTarget

from pyct import run_concolic
from pyct.config.execution import ExecutionConfig

_PAPER_TARGET_NAMES = (
    "Email Validation",
    "URL Routing",
    "Log Level Routing",
    "Triangle Classification",
    "Tax Bracket Calculator",
    "BMI Risk Classifier",
)


def _resolve_paper_target(name: str) -> BenchmarkTarget:
    for target in TEST_SUITE:
        if target.name == name:
            return target
    raise LookupError(f"paper target not found: {name}")


@pytest.fixture(scope="module")
def execution_config() -> ExecutionConfig:
    """Tight budget — gate is about pipeline correctness, not high coverage."""
    return ExecutionConfig(
        timeout_seconds=10.0,
        solver_timeout=5,
        max_iterations=20,
    )


@pytest.mark.parametrize("target_name", _PAPER_TARGET_NAMES)
def test_pure_concolic_runs_each_paper_target(target_name, execution_config):
    """Each paper target runs through pure concolic without raising."""
    target = _resolve_paper_target(target_name)
    import importlib

    module = importlib.import_module(target.module)
    func = getattr(module, target.function)

    result = run_concolic(
        func,
        dict(target.initial_args),
        config=execution_config,
        isolated=True,
    )

    assert result.success, f"{target_name} engine returned success=False: error={result.error}"
    # The engine should at least exercise the initial seed.
    assert len(result.inputs_generated) >= 1, f"{target_name}: expected at least one InputRecord"


@pytest.mark.parametrize("target_name", _PAPER_TARGET_NAMES)
def test_telemetry_counters_are_non_negative_ints(target_name, execution_config):
    """All four counters land as non-negative ints on every paper target."""
    target = _resolve_paper_target(target_name)
    import importlib

    module = importlib.import_module(target.module)
    func = getattr(module, target.function)

    result = run_concolic(
        func,
        dict(target.initial_args),
        config=execution_config,
        isolated=True,
    )

    for counter_name in ("gen_unsat", "gen_unknown", "gen_parse_failed", "harness_error"):
        value = getattr(result, counter_name)
        assert isinstance(value, int), f"{target_name}.{counter_name} not int: {value!r}"
        assert value >= 0, f"{target_name}.{counter_name} negative: {value}"


@pytest.mark.parametrize("target_name", _PAPER_TARGET_NAMES)
def test_runner_result_records_serialize_to_json_dicts(target_name, execution_config):
    """``_pyct_result_to_runner`` produces a ``RunnerResult`` whose
    ``input_records`` round-trips through ``json.dumps``.
    """
    target = _resolve_paper_target(target_name)
    import importlib

    module = importlib.import_module(target.module)
    func = getattr(module, target.function)

    raw_result = run_concolic(
        func,
        dict(target.initial_args),
        config=execution_config,
        isolated=True,
    )
    runner_result = _pyct_result_to_runner(raw_result, target, elapsed=0.0)

    assert isinstance(runner_result, RunnerResult)
    assert isinstance(runner_result.input_records, list)
    # Every record carries the four required keys.
    for record in runner_result.input_records:
        assert set(record.keys()) >= {"args", "provenance", "outcome", "new_lines", "error"}

    # JSON round-trip via the writer's repr fallback.
    payload = runner_result.to_dict()
    json.dumps(payload, default=repr)


def test_aggregate_results_json_round_trips(tmp_path, execution_config):
    """Run all six paper targets, aggregate into a results-shaped payload,
    and confirm ``save_results_json`` writes a parseable JSON file.

    Exercises the full ``RunnerResult`` → ``save_results_json`` path the
    per-input telemetry sub-tasks taught the benchmark layer.
    """
    import importlib

    all_results: list[dict] = []
    for target_name in _PAPER_TARGET_NAMES:
        target = _resolve_paper_target(target_name)
        module = importlib.import_module(target.module)
        func = getattr(module, target.function)
        raw_result = run_concolic(
            func,
            dict(target.initial_args),
            config=execution_config,
            isolated=True,
        )
        runner_result = _pyct_result_to_runner(raw_result, target, elapsed=0.0)
        all_results.append(
            {
                "target": target.name,
                "runner_results": {"pure_concolic": runner_result.to_dict()},
            }
        )

    out: Path = tmp_path / "results.json"
    save_results_json(all_results, BenchmarkConfig(), out)

    # Re-read and confirm shape.
    payload = json.loads(out.read_text())
    targets_in_payload = [entry["target"] for entry in payload["results"]]
    assert set(targets_in_payload) == set(_PAPER_TARGET_NAMES)

    for entry in payload["results"]:
        runner_payload = entry["runner_results"]["pure_concolic"]
        assert "input_records" in runner_payload
        assert runner_payload["gen_unsat"] >= 0
        assert runner_payload["gen_unknown"] >= 0
        assert runner_payload["gen_parse_failed"] >= 0
        assert runner_payload["harness_error"] >= 0
