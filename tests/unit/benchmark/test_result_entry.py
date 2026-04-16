"""Per-target result dict schema — baseline metadata propagation.

``results.json`` records which baseline a run was measured against so
stale-baseline drift is detectable later. The baseline timestamp (or
``None`` when no baseline was used) is stamped into each per-target
entry.
"""

from __future__ import annotations

from tools.benchmark.baseline import BASELINE_SCHEMA_VERSION, Baseline
from tools.benchmark.cli import _build_result_entry
from tools.benchmark.targets import BenchmarkTarget


def _target() -> BenchmarkTarget:
    return BenchmarkTarget(
        name="yaml.safe_load",
        module="yaml",
        function="safe_load",
        category="pyyaml",
        description="...",
    )


def test_result_entry_baseline_field_none_when_no_baseline():
    entry = _build_result_entry(_target(), runner_results={}, baseline=None)

    assert entry["baseline_generated_at"] is None


def test_result_entry_carries_baseline_timestamp_when_baseline_used():
    baseline = Baseline(
        target="yaml.safe_load",
        scopes=(),
        generated_at="2026-04-17T10:30:00",
        generator_version=BASELINE_SCHEMA_VERSION,
    )

    entry = _build_result_entry(_target(), runner_results={}, baseline=baseline)

    assert entry["baseline_generated_at"] == "2026-04-17T10:30:00"


def test_result_entry_preserves_existing_fields():
    # Adding baseline_generated_at must not drop the schema-matched fields
    # downstream summary writers already depend on.
    entry = _build_result_entry(_target(), runner_results={}, baseline=None)

    assert entry["test_name"] == "yaml.safe_load"
    assert entry["function"] == "safe_load"
    assert entry["category"] == "pyyaml"
    assert entry["runners"] == {}
