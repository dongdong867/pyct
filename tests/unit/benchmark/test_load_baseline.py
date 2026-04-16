"""Baseline lookup used by ``_measure_coverage`` at benchmark-run time.

Baselines are written by the generator under
``benchmark/baselines/{suite}/{target.name}.json``. The loader
glob-searches the root so runner code doesn't need to know which
suite a target belongs to. Missing / malformed / schema-mismatched
baselines return ``None`` — runners fall back to function-scope.
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.benchmark.baseline import BASELINE_SCHEMA_VERSION, Baseline, FunctionScope
from tools.benchmark.runners import _load_baseline
from tools.benchmark.targets import BenchmarkTarget


def _target(name: str = "yaml.safe_load") -> BenchmarkTarget:
    return BenchmarkTarget(
        name=name,
        module="yaml",
        function="safe_load",
        initial_args={"stream": ""},
        source_path="/fake/site-packages/yaml",
    )


def _write_baseline(path: Path, *, schema: str = BASELINE_SCHEMA_VERSION) -> None:
    baseline = Baseline(
        target="yaml.safe_load",
        scopes=(FunctionScope("yaml/__init__.py", 1, 5, (1, 2, 3)),),
        generated_at="2026-04-17T00:00:00",
        generator_version=schema,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    baseline.to_json(path)


def test_load_baseline_finds_file_under_library_subdir(tmp_path):
    _write_baseline(tmp_path / "library" / "yaml.safe_load.json")

    baseline = _load_baseline(_target(), baselines_root=tmp_path)

    assert baseline is not None
    assert baseline.target == "yaml.safe_load"


def test_load_baseline_finds_file_under_realworld_subdir(tmp_path):
    _write_baseline(tmp_path / "realworld" / "yaml.safe_load.json")

    baseline = _load_baseline(_target(), baselines_root=tmp_path)

    assert baseline is not None


def test_load_baseline_returns_none_when_no_baseline_for_target(tmp_path):
    _write_baseline(tmp_path / "library" / "other.target.json")

    baseline = _load_baseline(_target(), baselines_root=tmp_path)

    assert baseline is None


def test_load_baseline_returns_none_when_root_missing(tmp_path):
    baseline = _load_baseline(_target(), baselines_root=tmp_path / "does_not_exist")

    assert baseline is None


def test_load_baseline_returns_none_on_malformed_json(tmp_path):
    bad = tmp_path / "library" / "yaml.safe_load.json"
    bad.parent.mkdir(parents=True)
    bad.write_text("{ this is not valid json")

    baseline = _load_baseline(_target(), baselines_root=tmp_path)

    assert baseline is None


def test_load_baseline_returns_none_on_schema_version_mismatch(tmp_path):
    # Simulating a future schema bump — old code should refuse to load.
    _write_baseline(
        tmp_path / "library" / "yaml.safe_load.json",
        schema="99",
    )

    baseline = _load_baseline(_target(), baselines_root=tmp_path)

    assert baseline is None


def test_load_baseline_returns_none_when_json_missing_required_keys(tmp_path):
    # Payload that parses but doesn't match the Baseline shape.
    bad = tmp_path / "library" / "yaml.safe_load.json"
    bad.parent.mkdir(parents=True)
    bad.write_text(json.dumps({"target": "yaml.safe_load"}))

    baseline = _load_baseline(_target(), baselines_root=tmp_path)

    assert baseline is None
