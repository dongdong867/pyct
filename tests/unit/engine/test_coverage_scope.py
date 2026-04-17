"""Unit tests for CoverageScope value object.

CoverageScope specifies which source files the engine tracks and which
executable lines count as 'fully covered'. Two factories build common
shapes: ``for_target`` for classical single-file concolic scope, and
``for_paths`` for multi-file scopes used by benchmarks that measure
coverage across a whole library package.
"""

from __future__ import annotations

import pickle
import textwrap

import pytest

from pyct.engine.coverage_scope import CoverageScope


def _write_module(tmp_path, name, body):
    """Write a Python source file for testing; return its absolute path."""
    path = tmp_path / name
    path.write_text(textwrap.dedent(body))
    return str(path)


class TestForTarget:
    def test_single_target_scope_tracks_only_target_file(self):
        def sample(x):
            return x + 1

        scope = CoverageScope.for_target(sample)
        assert len(scope.files) == 1
        # Target's own file is in the scope
        target_file = next(iter(scope.files))
        assert target_file.endswith(".py")
        assert scope.target_file == target_file

    def test_for_target_populates_executable_lines_for_target_file(self):
        def sample(x):
            if x > 0:
                return "pos"
            return "np"

        scope = CoverageScope.for_target(sample)
        # At least the function body lines are present
        lines = scope.executable_lines[scope.target_file]
        assert len(lines) >= 2

    def test_for_target_marks_def_line_as_pre_covered(self):
        def sample():
            return None

        scope = CoverageScope.for_target(sample)
        pre = scope.pre_covered[scope.target_file]
        assert len(pre) == 1  # exactly the def line


class TestForPaths:
    def test_for_paths_tracks_multiple_files(self, tmp_path):
        f1 = _write_module(tmp_path, "a.py", "def f():\n    return 1\n")
        f2 = _write_module(tmp_path, "b.py", "def g():\n    return 2\n")

        scope = CoverageScope.for_paths([f1, f2])
        assert scope.files == frozenset({f1, f2})

    def test_for_paths_computes_executable_lines_per_file(self, tmp_path):
        small = "def f():\n    return 1\n"
        big = "def g(x):\n    if x:\n        return 1\n    return 0\n"
        f1 = _write_module(tmp_path, "one.py", small)
        f2 = _write_module(tmp_path, "two.py", big)

        scope = CoverageScope.for_paths([f1, f2])
        # Each file gets its own executable-line set
        assert len(scope.executable_lines[f1]) >= 1
        assert len(scope.executable_lines[f2]) >= 3

    def test_for_paths_raises_on_empty_iterable(self):
        with pytest.raises(ValueError):
            CoverageScope.for_paths([])

    def test_for_paths_accepts_optional_pre_covered(self, tmp_path):
        f1 = _write_module(tmp_path, "x.py", "def f():\n    return 1\n")

        scope = CoverageScope.for_paths([f1], pre_covered={f1: frozenset({1})})
        assert scope.pre_covered[f1] == frozenset({1})

    def test_for_paths_defaults_target_file_to_first_path(self, tmp_path):
        f1 = _write_module(tmp_path, "first.py", "def f():\n    return 1\n")
        f2 = _write_module(tmp_path, "second.py", "def g():\n    return 2\n")

        scope = CoverageScope.for_paths([f1, f2])
        assert scope.target_file == f1

    def test_for_paths_accepts_explicit_target_file(self, tmp_path):
        f1 = _write_module(tmp_path, "first.py", "def f():\n    return 1\n")
        f2 = _write_module(tmp_path, "second.py", "def g():\n    return 2\n")

        scope = CoverageScope.for_paths([f1, f2], target_file=f2)
        assert scope.target_file == f2


class TestTotalLines:
    def test_total_lines_sums_across_files(self, tmp_path):
        big = "def g(x):\n    if x:\n        return 1\n    return 0\n"
        f1 = _write_module(tmp_path, "a.py", "def f():\n    return 1\n")
        f2 = _write_module(tmp_path, "b.py", big)

        scope = CoverageScope.for_paths([f1, f2])
        expected = sum(len(v) for v in scope.executable_lines.values())
        assert scope.total_lines == expected

    def test_total_lines_zero_when_all_files_empty(self, tmp_path):
        f1 = _write_module(tmp_path, "empty.py", "")

        scope = CoverageScope.for_paths([f1])
        assert scope.total_lines == 0


class TestPickleRoundTrip:
    def test_pickle_preserves_equality(self, tmp_path):
        f1 = _write_module(tmp_path, "a.py", "def f():\n    return 1\n")

        scope = CoverageScope.for_paths([f1])
        restored = pickle.loads(pickle.dumps(scope))
        assert restored == scope

    def test_pickle_preserves_multi_file_scope(self, tmp_path):
        f1 = _write_module(tmp_path, "a.py", "def f():\n    return 1\n")
        f2 = _write_module(tmp_path, "b.py", "def g():\n    return 2\n")

        scope = CoverageScope.for_paths([f1, f2], target_file=f2)
        restored = pickle.loads(pickle.dumps(scope))
        assert restored.files == scope.files
        assert restored.executable_lines == scope.executable_lines
        assert restored.target_file == scope.target_file
