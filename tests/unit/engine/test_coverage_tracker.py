"""Unit tests for CoverageTracker.

The tracker consumes an immutable ``CoverageScope`` specifying which
source files to measure and which lines within each file are executable.
It exposes two views:

- Narrow view (``target_file``, ``covered_lines``, ``observed_lines``,
  ``function_lines``) — reports only the scope's primary target file.
  Used by plugin snapshots and ``ExplorationResult.executed_lines`` so
  LLM prompts keep reasoning about the target function.
- Wide view (``total_lines``, ``covered_count``, ``observed_count``,
  ``coverage_percent``, ``is_fully_covered``) — spans all scope files.
  Used by the engine for termination and plateau decisions.
"""

from __future__ import annotations

from coverage import CoverageData

from pyct.engine.coverage_scope import CoverageScope
from pyct.engine.coverage_tracker import CoverageTracker


class TestSingleFileScope:
    def test_tracker_exposes_target_file_from_scope(self, tmp_path):
        target = str(tmp_path / "target.py")
        scope = CoverageScope.for_file(target, frozenset({1, 2, 3}))
        tracker = CoverageTracker(scope)
        assert tracker.target_file == target

    def test_function_lines_reflects_target_file_executable_lines(self, tmp_path):
        target = str(tmp_path / "t.py")
        scope = CoverageScope.for_file(target, frozenset({1, 2, 3, 4, 5}))
        tracker = CoverageTracker(scope)
        assert tracker.function_lines == frozenset({1, 2, 3, 4, 5})

    def test_total_lines_matches_executable_count(self, tmp_path):
        target = str(tmp_path / "t.py")
        scope = CoverageScope.for_file(target, frozenset({1, 2, 3, 4, 5}))
        tracker = CoverageTracker(scope)
        assert tracker.total_lines == 5

    def test_covered_lines_empty_before_any_update(self, tmp_path):
        target = str(tmp_path / "t.py")
        scope = CoverageScope.for_file(target, frozenset({1, 2, 3}))
        tracker = CoverageTracker(scope)
        assert tracker.covered_lines == frozenset()

    def test_update_accumulates_executed_lines(self, tmp_path):
        target = str(tmp_path / "t.py")
        scope = CoverageScope.for_file(target, frozenset({1, 2, 3, 4, 5}))
        tracker = CoverageTracker(scope)

        data = CoverageData(basename=str(tmp_path / "cov1.data"))
        data.add_lines({target: [1, 3, 5]})
        tracker.update(data)

        assert tracker.covered_lines == frozenset({1, 3, 5})

    def test_multiple_updates_are_cumulative(self, tmp_path):
        target = str(tmp_path / "t.py")
        scope = CoverageScope.for_file(target, frozenset({1, 2, 3, 4, 5}))
        tracker = CoverageTracker(scope)

        data1 = CoverageData(basename=str(tmp_path / "cov1.data"))
        data1.add_lines({target: [1, 2]})
        tracker.update(data1)

        data2 = CoverageData(basename=str(tmp_path / "cov2.data"))
        data2.add_lines({target: [3, 4]})
        tracker.update(data2)

        assert tracker.covered_lines == frozenset({1, 2, 3, 4})

    def test_update_filters_lines_outside_executable_set(self, tmp_path):
        target = str(tmp_path / "t.py")
        scope = CoverageScope.for_file(target, frozenset({5, 6, 7}))
        tracker = CoverageTracker(scope)

        data = CoverageData(basename=str(tmp_path / "cov.data"))
        data.add_lines({target: [1, 5, 6, 10]})
        tracker.update(data)

        assert tracker.covered_lines == frozenset({5, 6})

    def test_update_with_unrelated_file_is_noop(self, tmp_path):
        target = str(tmp_path / "t.py")
        other = str(tmp_path / "other.py")
        scope = CoverageScope.for_file(target, frozenset({1, 2, 3}))
        tracker = CoverageTracker(scope)

        data = CoverageData(basename=str(tmp_path / "cov.data"))
        data.add_lines({other: [1, 2]})
        tracker.update(data)

        assert tracker.covered_lines == frozenset()


class TestIsFullyCoveredSingleFile:
    def test_false_until_all_executable_lines_hit(self, tmp_path):
        target = str(tmp_path / "t.py")
        scope = CoverageScope.for_file(target, frozenset({1, 2, 3}))
        tracker = CoverageTracker(scope)
        assert tracker.is_fully_covered() is False

        data = CoverageData(basename=str(tmp_path / "cov.data"))
        data.add_lines({target: [1, 2]})
        tracker.update(data)
        assert tracker.is_fully_covered() is False

    def test_true_when_all_executable_lines_hit(self, tmp_path):
        target = str(tmp_path / "t.py")
        scope = CoverageScope.for_file(target, frozenset({1, 2, 3}))
        tracker = CoverageTracker(scope)

        data = CoverageData(basename=str(tmp_path / "cov.data"))
        data.add_lines({target: [1, 2, 3]})
        tracker.update(data)

        assert tracker.is_fully_covered() is True

    def test_pre_covered_lines_count_toward_full_coverage(self, tmp_path):
        target = str(tmp_path / "t.py")
        scope = CoverageScope.for_file(
            target,
            frozenset({1, 2, 3}),
            pre_covered=frozenset({1}),
        )
        tracker = CoverageTracker(scope)

        data = CoverageData(basename=str(tmp_path / "cov.data"))
        data.add_lines({target: [2, 3]})
        tracker.update(data)

        assert tracker.is_fully_covered() is True


class TestDegenerate:
    def test_empty_executable_lines_reports_zero_total_and_covered(self, tmp_path):
        scope = CoverageScope.for_file(str(tmp_path / "t.py"), frozenset())
        tracker = CoverageTracker(scope)
        assert tracker.total_lines == 0
        assert tracker.is_fully_covered() is True


class TestMultiFileScope:
    """Wide scope behavior — tracker spans multiple files."""

    def _two_file_scope(self, tmp_path):
        f1 = str(tmp_path / "a.py")
        f2 = str(tmp_path / "b.py")
        scope = CoverageScope(
            files=frozenset({f1, f2}),
            executable_lines={f1: frozenset({1, 2}), f2: frozenset({3, 4, 5})},
            pre_covered={},
            target_file=f1,
        )
        return f1, f2, scope

    def test_total_lines_sums_across_files(self, tmp_path):
        _, _, scope = self._two_file_scope(tmp_path)
        tracker = CoverageTracker(scope)
        assert tracker.total_lines == 5  # 2 + 3

    def test_update_accumulates_per_file(self, tmp_path):
        f1, f2, scope = self._two_file_scope(tmp_path)
        tracker = CoverageTracker(scope)

        data = CoverageData(basename=str(tmp_path / "cov.data"))
        data.add_lines({f1: [1, 2], f2: [3]})
        tracker.update(data)

        assert tracker.observed_count == 3

    def test_is_fully_covered_requires_every_file(self, tmp_path):
        f1, f2, scope = self._two_file_scope(tmp_path)
        tracker = CoverageTracker(scope)

        # Cover all of f1 but only part of f2 — not full
        data = CoverageData(basename=str(tmp_path / "cov.data"))
        data.add_lines({f1: [1, 2], f2: [3]})
        tracker.update(data)
        assert tracker.is_fully_covered() is False

        # Add the remaining f2 lines — now full
        more = CoverageData(basename=str(tmp_path / "cov2.data"))
        more.add_lines({f2: [4, 5]})
        tracker.update(more)
        assert tracker.is_fully_covered() is True

    def test_narrow_views_report_target_file_only(self, tmp_path):
        f1, f2, scope = self._two_file_scope(tmp_path)  # target_file == f1
        tracker = CoverageTracker(scope)

        data = CoverageData(basename=str(tmp_path / "cov.data"))
        data.add_lines({f1: [1], f2: [3, 4]})
        tracker.update(data)

        # Narrow: only f1's coverage
        assert tracker.covered_lines == frozenset({1})
        assert tracker.observed_lines == frozenset({1})
        assert tracker.function_lines == frozenset({1, 2})

    def test_coverage_percent_spans_scope(self, tmp_path):
        f1, f2, scope = self._two_file_scope(tmp_path)
        tracker = CoverageTracker(scope)

        data = CoverageData(basename=str(tmp_path / "cov.data"))
        # 1 of 5 total covered
        data.add_lines({f1: [1]})
        tracker.update(data)

        assert tracker.coverage_percent == 20.0

    def test_covered_count_includes_pre_covered_per_file(self, tmp_path):
        f1 = str(tmp_path / "a.py")
        f2 = str(tmp_path / "b.py")
        scope = CoverageScope(
            files=frozenset({f1, f2}),
            executable_lines={f1: frozenset({1, 2}), f2: frozenset({3, 4})},
            pre_covered={f1: frozenset({1})},
            target_file=f1,
        )
        tracker = CoverageTracker(scope)
        # Pre-covered f1:1 alone → covered_count=1
        assert tracker.covered_count == 1
