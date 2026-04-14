"""Tests for SolverStats."""

from __future__ import annotations

from pyct.solver.stats import SolverStats


class TestSolverStats:
    """SolverStats tracks SAT/UNSAT/UNKNOWN counts and times."""

    def test_initial_counts_zero(self):
        stats = SolverStats()
        assert stats.sat_number == 0
        assert stats.unsat_number == 0
        assert stats.otherwise_number == 0

    def test_record_sat_increments(self):
        stats = SolverStats()
        stats.record_sat(1.5)
        assert stats.sat_number == 1
        assert stats.sat_time == 1.5

    def test_record_unsat_increments(self):
        stats = SolverStats()
        stats.record_unsat(0.5)
        assert stats.unsat_number == 1
        assert stats.unsat_time == 0.5

    def test_record_unknown_increments(self):
        stats = SolverStats()
        stats.record_unknown(2.0)
        assert stats.otherwise_number == 1
        assert stats.otherwise_time == 2.0

    def test_to_dict_correct_format(self):
        stats = SolverStats()
        stats.record_sat(1.0)
        stats.record_unsat(0.5)
        d = stats.to_dict()
        assert d["sat_number"] == 1
        assert d["sat_time"] == 1.0
        assert d["unsat_number"] == 1
        assert d["unsat_time"] == 0.5
        assert d["otherwise_number"] == 0


class TestSolverStatsBoundary:
    """Boundary and cumulative-behavior characterization."""

    def test_record_sat_with_zero_elapsed_time_accepted(self):
        stats = SolverStats()
        stats.record_sat(0.0)
        assert stats.sat_number == 1
        assert stats.sat_time == 0.0

    def test_multiple_sat_records_accumulate_count_and_time(self):
        stats = SolverStats()
        stats.record_sat(0.5)
        stats.record_sat(1.0)
        stats.record_sat(0.25)
        assert stats.sat_number == 3
        assert stats.sat_time == 1.75

    def test_mixed_record_calls_increment_counters_independently(self):
        stats = SolverStats()
        stats.record_sat(1.0)
        stats.record_unsat(0.5)
        stats.record_unknown(2.0)
        stats.record_sat(0.25)
        assert stats.sat_number == 2
        assert stats.unsat_number == 1
        assert stats.otherwise_number == 1


class TestSolverStatsLoose:
    """Characterization tests documenting lack of input validation."""

    def test_record_sat_with_negative_elapsed_accepted(self):
        # SolverStats does not validate — negative times are stored as-is.
        # Locked as characterization so any future validation is intentional.
        stats = SolverStats()
        stats.record_sat(-1.5)
        assert stats.sat_number == 1
        assert stats.sat_time == -1.5

    def test_to_dict_returns_all_six_fields(self):
        stats = SolverStats()
        d = stats.to_dict()
        expected_keys = {
            "sat_number",
            "sat_time",
            "unsat_number",
            "unsat_time",
            "otherwise_number",
            "otherwise_time",
        }
        assert set(d.keys()) == expected_keys
