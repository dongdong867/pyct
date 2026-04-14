"""Unit tests for CoverageTracker."""

from __future__ import annotations

from coverage import CoverageData

from pyct.engine.coverage_tracker import CoverageTracker


class TestCoverageTrackerConstruction:
    def test_tracker_constructs_with_target_file_and_function_lines(self, tmp_path):
        target = str(tmp_path / "target.py")
        tracker = CoverageTracker(target, frozenset({1, 2, 3}))
        assert tracker.target_file == target
        assert tracker.function_lines == frozenset({1, 2, 3})

    def test_total_lines_matches_function_lines_count(self, tmp_path):
        tracker = CoverageTracker(str(tmp_path / "t.py"), frozenset({1, 2, 3, 4, 5}))
        assert tracker.total_lines == 5

    def test_covered_lines_empty_before_any_update(self, tmp_path):
        tracker = CoverageTracker(str(tmp_path / "t.py"), frozenset({1, 2, 3}))
        assert tracker.covered_lines == frozenset()

    def test_covered_lines_returns_frozenset(self, tmp_path):
        tracker = CoverageTracker(str(tmp_path / "t.py"), frozenset({1, 2}))
        assert isinstance(tracker.covered_lines, frozenset)


class TestCoverageTrackerUpdate:
    def test_update_accumulates_executed_lines(self, tmp_path):
        target = str(tmp_path / "t.py")
        tracker = CoverageTracker(target, frozenset({1, 2, 3, 4, 5}))

        data = CoverageData(basename=str(tmp_path / "cov1.data"))
        data.add_lines({target: [1, 3, 5]})
        tracker.update(data)

        assert tracker.covered_lines == frozenset({1, 3, 5})

    def test_multiple_updates_are_cumulative(self, tmp_path):
        target = str(tmp_path / "t.py")
        tracker = CoverageTracker(target, frozenset({1, 2, 3, 4, 5}))

        data1 = CoverageData(basename=str(tmp_path / "cov1.data"))
        data1.add_lines({target: [1, 2]})
        tracker.update(data1)

        data2 = CoverageData(basename=str(tmp_path / "cov2.data"))
        data2.add_lines({target: [3, 4]})
        tracker.update(data2)

        assert tracker.covered_lines == frozenset({1, 2, 3, 4})

    def test_update_filters_lines_outside_function_range(self, tmp_path):
        target = str(tmp_path / "t.py")
        # Function occupies lines 5-7 only; lines 1 and 10 are outside the
        # function but might still show up in raw coverage data.
        tracker = CoverageTracker(target, frozenset({5, 6, 7}))

        data = CoverageData(basename=str(tmp_path / "cov.data"))
        data.add_lines({target: [1, 5, 6, 10]})
        tracker.update(data)

        # Only the in-range lines are recorded
        assert tracker.covered_lines == frozenset({5, 6})

    def test_update_with_coverage_data_missing_target_file_is_noop(self, tmp_path):
        target = str(tmp_path / "t.py")
        other = str(tmp_path / "other.py")
        tracker = CoverageTracker(target, frozenset({1, 2, 3}))

        data = CoverageData(basename=str(tmp_path / "cov.data"))
        # Coverage data only for a different file — target_file is absent
        data.add_lines({other: [1, 2]})
        tracker.update(data)

        assert tracker.covered_lines == frozenset()


class TestIsFullyCovered:
    def test_is_fully_covered_false_until_all_lines_hit(self, tmp_path):
        target = str(tmp_path / "t.py")
        tracker = CoverageTracker(target, frozenset({1, 2, 3}))
        assert tracker.is_fully_covered() is False

        data = CoverageData(basename=str(tmp_path / "cov.data"))
        data.add_lines({target: [1, 2]})
        tracker.update(data)
        assert tracker.is_fully_covered() is False

    def test_is_fully_covered_true_when_all_lines_hit(self, tmp_path):
        target = str(tmp_path / "t.py")
        tracker = CoverageTracker(target, frozenset({1, 2, 3}))

        data = CoverageData(basename=str(tmp_path / "cov.data"))
        data.add_lines({target: [1, 2, 3]})
        tracker.update(data)

        assert tracker.is_fully_covered() is True


class TestCoverageTrackerDegenerate:
    def test_empty_function_lines_reports_zero_total_and_fully_covered(self, tmp_path):
        # Degenerate but correct: empty >= empty is True
        tracker = CoverageTracker(str(tmp_path / "t.py"), frozenset())
        assert tracker.total_lines == 0
        assert tracker.is_fully_covered() is True
