"""Unit tests for ExplorationState (internal, mutable)."""

import time

from pyct.engine.coverage_scope import CoverageScope
from pyct.engine.coverage_tracker import CoverageTracker
from pyct.engine.state import ExplorationState
from pyct.engine.types import InputRecord, Outcome, Provenance


def _record(args: dict) -> InputRecord:
    """Build a placeholder record for tests that only care about list length."""
    return InputRecord(
        args=args,
        provenance=Provenance.SEED,
        outcome=Outcome.NO_GAIN,
        new_lines=frozenset(),
        error=None,
    )


class TestExplorationStateDefaults:
    def test_starts_at_iteration_zero(self):
        state = ExplorationState()
        assert state.iteration == 0

    def test_starts_with_empty_constraint_pool(self):
        state = ExplorationState()
        assert state.constraint_pool == []

    def test_starts_with_empty_covered_lines(self):
        state = ExplorationState()
        assert state.covered_lines == set()

    def test_starts_with_zero_total_lines(self):
        state = ExplorationState()
        assert state.total_lines == 0

    def test_starts_with_empty_records(self):
        state = ExplorationState()
        assert state.records == []

    def test_starts_not_terminated(self):
        state = ExplorationState()
        assert state.terminated is False

    def test_starts_with_no_termination_reason(self):
        state = ExplorationState()
        assert state.termination_reason is None

    def test_starts_with_empty_pre_cover_lines(self):
        state = ExplorationState()
        assert state.pre_cover_lines == frozenset()
        assert isinstance(state.pre_cover_lines, frozenset)

    def test_starts_with_zero_non_execution_counters(self):
        state = ExplorationState()
        assert state.gen_unsat == 0
        assert state.gen_unknown == 0
        assert state.harness_error == 0


class TestExplorationStateCoverage:
    def test_coverage_percent_zero_when_no_total_lines(self):
        state = ExplorationState(total_lines=0)
        assert state.coverage_percent() == 0.0

    def test_coverage_percent_zero_when_no_covered_lines(self):
        state = ExplorationState(total_lines=10)
        assert state.coverage_percent() == 0.0

    def test_coverage_percent_fifty_when_half_covered(self):
        state = ExplorationState(total_lines=10, covered_lines={1, 2, 3, 4, 5})
        assert state.coverage_percent() == 50.0

    def test_coverage_percent_full_when_all_covered(self):
        state = ExplorationState(
            total_lines=10,
            covered_lines={1, 2, 3, 4, 5, 6, 7, 8, 9, 10},
        )
        assert state.coverage_percent() == 100.0


class TestExplorationStatePaths:
    def test_paths_explored_counts_records(self):
        state = ExplorationState()
        state.records.append(_record({"x": 1}))
        state.records.append(_record({"x": 2}))
        assert state.paths_explored() == 2

    def test_has_seen_args_returns_true_for_existing_args(self):
        state = ExplorationState()
        state.records.append(_record({"x": 1}))
        assert state.has_seen_args({"x": 1}) is True

    def test_has_seen_args_returns_false_for_unseen_args(self):
        state = ExplorationState()
        state.records.append(_record({"x": 1}))
        assert state.has_seen_args({"x": 2}) is False

    def test_has_seen_args_empty_state(self):
        state = ExplorationState()
        assert state.has_seen_args({"x": 1}) is False

    def test_paths_explored_zero_initially(self):
        state = ExplorationState()
        assert state.paths_explored() == 0


class TestExplorationStateElapsed:
    def test_elapsed_seconds_positive_after_sleep(self):
        state = ExplorationState(start_time=time.monotonic())
        time.sleep(0.01)
        assert state.elapsed_seconds() > 0

    def test_elapsed_seconds_zero_when_start_time_now(self):
        state = ExplorationState(start_time=time.monotonic())
        # Immediately after — should be near zero
        assert state.elapsed_seconds() < 0.1


class TestExplorationStateBoundary:
    """Characterization tests for boundary and degenerate states."""

    def test_coverage_percent_unclamped_when_covered_exceeds_total(self):
        # Current behavior is to not clamp above 100%. If covered > total
        # (which shouldn't happen in practice), the percent runs away.
        # This test documents the lack of clamping so any future change
        # to add clamping becomes an intentional decision, not a silent
        # behavior shift.
        state = ExplorationState(
            total_lines=10,
            covered_lines={1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12},
        )
        assert state.coverage_percent() == 120.0

    def test_state_is_not_frozen_and_fields_are_mutable(self):
        state = ExplorationState()
        state.iteration = 5
        state.terminated = True
        assert state.iteration == 5
        assert state.terminated is True

    def test_elapsed_seconds_with_zero_start_time_returns_monotonic_time(self):
        state = ExplorationState()  # start_time defaults to 0.0
        elapsed = state.elapsed_seconds()
        # With start_time=0.0, elapsed equals monotonic() itself — a large
        # number, not zero. Engine must set start_time before measuring.
        assert elapsed > 0.0
        assert elapsed >= time.monotonic() - 1.0


class TestExplorationStateScopeViews:
    """Wide-scope views forward to an optional tracker.

    These views let the engine reason about scope-spanning coverage
    (multiple files when scope is wide) without touching the narrow
    ``covered_lines`` / ``total_lines`` fields that plugin snapshots
    and legacy callers depend on.
    """

    def _tracker_with_scope(self, tmp_path, executable_lines):
        path = str(tmp_path / "t.py")
        scope = CoverageScope.for_file(path, frozenset(executable_lines))
        return path, CoverageTracker(scope)

    def test_scope_views_zero_when_tracker_is_none(self):
        state = ExplorationState()
        assert state.tracker is None
        assert state.scope_total_lines == 0
        assert state.scope_observed_count == 0
        assert state.scope_covered_count == 0
        assert state.scope_coverage_percent() == 0.0

    def test_scope_total_lines_forwards_to_tracker(self, tmp_path):
        _, tracker = self._tracker_with_scope(tmp_path, {1, 2, 3, 4, 5})
        state = ExplorationState(tracker=tracker)
        assert state.scope_total_lines == 5

    def test_scope_observed_count_reflects_tracker_observed_count(self, tmp_path):
        from coverage import CoverageData

        path, tracker = self._tracker_with_scope(tmp_path, {1, 2, 3, 4, 5})
        state = ExplorationState(tracker=tracker)

        data = CoverageData(basename=str(tmp_path / "cov.data"))
        data.add_lines({path: [1, 3]})
        tracker.update(data)

        assert state.scope_observed_count == 2

    def test_scope_covered_count_includes_pre_covered(self, tmp_path):
        path = str(tmp_path / "t.py")
        scope = CoverageScope.for_file(path, frozenset({1, 2, 3}), pre_covered=frozenset({1}))
        tracker = CoverageTracker(scope)
        state = ExplorationState(tracker=tracker)
        # No observed updates; just pre-covered counts
        assert state.scope_covered_count == 1

    def test_scope_coverage_percent_uses_wide_ratio(self, tmp_path):
        from coverage import CoverageData

        path, tracker = self._tracker_with_scope(tmp_path, {1, 2, 3, 4})
        state = ExplorationState(tracker=tracker)

        data = CoverageData(basename=str(tmp_path / "cov.data"))
        data.add_lines({path: [1]})
        tracker.update(data)

        assert state.scope_coverage_percent() == 25.0

    def test_narrow_fields_remain_independent_of_tracker(self, tmp_path):
        _, tracker = self._tracker_with_scope(tmp_path, {1, 2, 3})
        state = ExplorationState(tracker=tracker, total_lines=10, covered_lines={1, 2})
        # Narrow view unchanged by tracker presence
        assert state.total_lines == 10
        assert state.covered_lines == {1, 2}
        assert state.coverage_percent() == 20.0
