"""``_measure_coverage`` dispatches on baseline presence.

When a committed baseline exists for the target, the function delegates
to ``measure_against_baseline``. When no baseline is present, it falls
through to the legacy function-scope path (covered by existing
acceptance tests; here we pin only the baseline branch).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tools.benchmark.baseline import BASELINE_SCHEMA_VERSION, Baseline, FunctionScope
from tools.benchmark.runners import _measure_coverage
from tools.benchmark.targets import BenchmarkTarget


@dataclass
class _FakeData:
    files: dict[str, list[int]]

    def measured_files(self) -> list[str]:
        return list(self.files.keys())

    def lines(self, path: str) -> list[int] | None:
        return self.files.get(path)


@dataclass
class _FakeSession:
    files: dict[str, list[int]] = field(default_factory=dict)

    def get_data(self) -> _FakeData:
        return _FakeData(self.files)


def _write_baseline(path, scope_lines: tuple[int, ...]) -> None:
    baseline = Baseline(
        target="yaml.safe_load",
        scopes=(FunctionScope("yaml/__init__.py", 1, 20, scope_lines),),
        generated_at="2026-04-17T00:00:00",
        generator_version=BASELINE_SCHEMA_VERSION,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    baseline.to_json(path)


def _target() -> BenchmarkTarget:
    # Module / function intentionally bogus — baseline path doesn't resolve them.
    return BenchmarkTarget(
        name="yaml.safe_load",
        module="yaml",
        function="safe_load",
        initial_args={"stream": ""},
        source_path="/fake/site-packages/yaml",
    )


def test_dispatch_uses_baseline_when_one_exists(tmp_path):
    _write_baseline(
        tmp_path / "library" / "yaml.safe_load.json",
        scope_lines=(1, 2, 3, 5),
    )
    session = _FakeSession({"/v/lib/python3.12/site-packages/yaml/__init__.py": [3, 5]})

    result = _measure_coverage(session, _target(), baselines_root=tmp_path)

    # Baseline has 4 lines; hits {3, 5} with def-line backfill → {1, 2, 3, 5} = 4
    assert result.total_lines == 4
    assert result.executed_lines == 4
    assert result.coverage_percent == 100.0


def test_dispatch_baseline_path_ignores_hits_outside_baseline_scope(tmp_path):
    _write_baseline(
        tmp_path / "library" / "yaml.safe_load.json",
        scope_lines=(1, 2, 3),
    )
    session = _FakeSession({"/v/lib/python3.12/site-packages/yaml/__init__.py": [2, 99, 100]})

    result = _measure_coverage(session, _target(), baselines_root=tmp_path)

    # Lines 99 / 100 are not in the baseline scope — only line 2 counts,
    # with def-line backfill → {1, 2} = 2 covered out of 3.
    assert result.total_lines == 3
    assert result.executed_lines == 2
