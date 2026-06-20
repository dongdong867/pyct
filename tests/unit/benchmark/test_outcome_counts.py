"""OutcomeCounts aggregates per-input outcomes into run-level metrics.

The reviewer-requested execution metrics — how many inputs exit cleanly,
how many end in an error, and how many trigger an AssertionError — are
pure derivations of the ``input_records`` every runner already captures
(each record's ``outcome`` and ``error`` fields). ``OutcomeCounts.
from_records`` folds a record list into those totals; the breakdown by
exception type names ``AssertionError`` explicitly so the
fault-triggering count is readable without post-processing.
"""

from __future__ import annotations

from tools.benchmark.models import OutcomeCounts


def _rec(outcome: str, error: str | None = None) -> dict:
    """Minimal input-record dict in the shape runners serialize."""
    return {
        "args": {},
        "provenance": "seed",
        "outcome": outcome,
        "new_lines": [],
        "error": error,
    }


class TestFromRecords:
    def test_empty_records_all_zero(self):
        counts = OutcomeCounts.from_records([])
        assert counts.total == 0
        assert counts.clean_exit == 0
        assert counts.error_exit == 0
        assert counts.timeout == 0
        assert counts.by_exception == {}

    def test_clean_exit_counts_covered_new_and_no_gain(self):
        counts = OutcomeCounts.from_records([_rec("covered_new"), _rec("no_gain")])
        assert counts.clean_exit == 2
        assert counts.error_exit == 0
        assert counts.timeout == 0
        assert counts.total == 2

    def test_error_exit_and_by_exception_breakdown(self):
        records = [
            _rec("target_error", "AssertionError: x > 10"),
            _rec("target_error", "AssertionError: y < 0"),
            _rec("target_error", "ValueError: bad input"),
        ]
        counts = OutcomeCounts.from_records(records)
        assert counts.error_exit == 3
        assert counts.by_exception == {"AssertionError": 2, "ValueError": 1}

    def test_timeout_counted_separately_from_error(self):
        counts = OutcomeCounts.from_records([_rec("timeout", "timeout: deadline exceeded")])
        assert counts.timeout == 1
        assert counts.error_exit == 0
        assert counts.by_exception == {}

    def test_systemexit_error_type_parsed_without_colon(self):
        # The engine formats SystemExit as "SystemExit(0)" — no colon to
        # split on. The parser must still bucket it as "SystemExit".
        counts = OutcomeCounts.from_records([_rec("target_error", "SystemExit(0)")])
        assert counts.by_exception == {"SystemExit": 1}
        assert counts.error_exit == 1

    def test_mixed_records_full_tally(self):
        records = [
            _rec("covered_new"),
            _rec("no_gain"),
            _rec("target_error", "AssertionError: boom"),
            _rec("timeout", "timeout: x"),
        ]
        counts = OutcomeCounts.from_records(records)
        assert counts.total == 4
        assert counts.clean_exit == 2
        assert counts.error_exit == 1
        assert counts.timeout == 1
        assert counts.by_exception == {"AssertionError": 1}

    def test_to_dict_shape(self):
        counts = OutcomeCounts.from_records([_rec("target_error", "AssertionError: z")])
        assert counts.to_dict() == {
            "total": 1,
            "clean_exit": 0,
            "error_exit": 1,
            "timeout": 0,
            "by_exception": {"AssertionError": 1},
        }
