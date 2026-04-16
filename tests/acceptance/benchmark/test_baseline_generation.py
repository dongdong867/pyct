"""End-to-end: run inputs under a broad coverage session → entered scopes.

These tests prove the filesystem + coverage.py + Python import seam
that unit tests cannot. They also cover ``_pyct_result_to_runner``'s
source_path branch, which re-runs inputs through ``coverage.py`` so
library/realworld runners can surface transitive coverage instead of
the engine's narrow per-file tracker.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from tools.benchmark.baseline_generator import collect_scopes_for_inputs
from tools.benchmark.runners import _pyct_result_to_runner
from tools.benchmark.targets import BenchmarkTarget


@pytest.fixture(autouse=True)
def _purge_synthpkg_from_sys_modules():
    """Each test writes fresh synthpkg files to a new tmp_path; stale
    imports cached in sys.modules would shadow them and coverage would
    measure paths that no longer exist on disk.
    """
    yield
    for name in list(sys.modules):
        if name == "synthpkg" or name.startswith("synthpkg."):
            del sys.modules[name]


@dataclass
class _FakeRunResult:
    """Stand-in for ``pyct.engine.result.RunConcolicResult``."""

    success: bool = True
    executed_lines: frozenset[int] = field(default_factory=frozenset)
    inputs_generated: tuple = ()
    error: str | None = None
    iterations: int = 0


def _write_synthetic_package(root: Path) -> Path:
    """Write a 2-file package where the entry dispatches to a helper."""
    pkg = root / "synthpkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "entry.py").write_text(
        "from synthpkg.helpers import classify\n\ndef entry(x):\n    return classify(x)\n"
    )
    (pkg / "helpers.py").write_text(
        "def classify(x):\n    if x > 0:\n        return 'positive'\n    return 'non-positive'\n"
    )
    return pkg


def test_broad_coverage_captures_scopes_across_files(tmp_path, monkeypatch):
    """Running an input that flows into a helper must register the helper's scope."""
    pkg_dir = _write_synthetic_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    target = BenchmarkTarget(
        name="synth",
        module="synthpkg.entry",
        function="entry",
        initial_args={"x": 0},
        source_path=str(pkg_dir),
    )
    # Inputs that exercise both branches in classify()
    inputs = [{"x": 5}, {"x": -5}]

    scopes = collect_scopes_for_inputs(target, inputs)

    files = {Path(s.file).name for s in scopes}
    assert "entry.py" in files, "Entry function scope missing"
    assert "helpers.py" in files, "Callee scope missing — coverage not widened"


def test_narrow_target_without_source_path_still_emits_entry_scope(tmp_path, monkeypatch):
    """Targets without source_path (standard suite) fall back to file-scoped coverage."""
    _write_synthetic_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    target = BenchmarkTarget(
        name="synth",
        module="synthpkg.entry",
        function="entry",
        initial_args={"x": 0},
        source_path=None,  # <-- narrow coverage
    )

    scopes = collect_scopes_for_inputs(target, [{"x": 1}])

    # Entry is measured (it's the target file); helper is NOT in scope.
    files = {Path(s.file).name for s in scopes}
    assert "entry.py" in files
    assert "helpers.py" not in files


def test_input_that_raises_does_not_abort_collection(tmp_path, monkeypatch):
    """One bad input must not sink the whole scope collection."""
    pkg_dir = _write_synthetic_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))

    target = BenchmarkTarget(
        name="synth",
        module="synthpkg.entry",
        function="entry",
        initial_args={"x": 0},
        source_path=str(pkg_dir),
    )
    # ``None`` triggers ``TypeError: '>' not supported between NoneType and int``
    inputs = [{"x": None}, {"x": 5}]

    scopes = collect_scopes_for_inputs(target, inputs)

    files = {Path(s.file).name for s in scopes}
    assert "helpers.py" in files, "Valid input after failing one should still measure"


# ── _pyct_result_to_runner — source_path re-run branch ────────────


def test_pyct_result_reruns_inputs_for_source_path_target(tmp_path, monkeypatch):
    """For library/realworld targets, coverage must be rebuilt by re-running
    the engine's discovered inputs through coverage.py — the engine's own
    per-line tracker is scoped to the entry file and cannot see callees.
    """
    pkg_dir = _write_synthetic_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    target = BenchmarkTarget(
        name="synth",
        module="synthpkg.entry",
        function="entry",
        initial_args={"x": 0},
        source_path=str(pkg_dir),
    )
    # Inputs that reach the `x > 0` branch inside classify()
    fake = _FakeRunResult(
        success=True,
        inputs_generated=({"x": 5},),
        executed_lines=frozenset(),  # intentionally empty — proves this isn't used
    )

    runner_result = _pyct_result_to_runner(fake, target, elapsed=1.0)

    # Without a committed baseline we fall back to function-scope on the entry
    # file — but crucially the coverage numbers are non-zero because the
    # inputs were actually executed under coverage.py rather than relying
    # on the empty engine tracker.
    assert runner_result.success
    assert runner_result.coverage.total_lines > 0
    assert runner_result.coverage.executed_lines > 0


def test_pyct_result_standard_target_falls_back_to_engine_tracker(tmp_path, monkeypatch):
    """For standard targets (no source_path), measurement stays on the
    legacy path: engine-reported executed_lines vs function-scope
    statements. Preserves comparability with pre-baseline paper data.
    """
    _write_synthetic_package(tmp_path)
    monkeypatch.syspath_prepend(str(tmp_path))
    target = BenchmarkTarget(
        name="synth",
        module="synthpkg.entry",
        function="entry",
        initial_args={"x": 0},
        source_path=None,  # <-- standard-style
    )
    # Engine reports def (3) + body (4) as executed — standard hit pattern.
    fake = _FakeRunResult(
        success=True,
        inputs_generated=(),  # intentionally empty — proves this isn't used
        executed_lines=frozenset({3, 4}),
    )

    runner_result = _pyct_result_to_runner(fake, target, elapsed=1.0)

    # entry() has 2 executable statements (def, return); both hit → 100%.
    assert runner_result.success
    assert runner_result.coverage.total_lines == 2
    assert runner_result.coverage.executed_lines == 2
