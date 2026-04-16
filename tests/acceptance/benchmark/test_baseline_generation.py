"""End-to-end: run inputs under a broad coverage session → entered scopes.

This is the integration test that proves the coverage.py widening
actually measures sub-callees when the target entry function delegates
to helpers in other files. The pure layers that compose into a
:class:`Baseline` are exercised in ``tests/unit/benchmark/``; this test
guards the filesystem + coverage.py + Python import seam that unit
tests cannot.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from tools.benchmark.baseline_generator import collect_scopes_for_inputs
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
