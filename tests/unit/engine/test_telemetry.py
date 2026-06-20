"""Unit tests for run-end telemetry: rewrite summary + target-error lines."""

import logging

from pyct.engine.state import ExplorationState
from pyct.engine.telemetry import emit_run_summary, emit_target_errors
from pyct.engine.types import InputRecord, Outcome, Provenance


class TestRewriteTelemetrySummary:
    # TDD path step: summary-line-emitted-per-target-runner
    def test_emits_one_info_line_when_a_firing_counter_is_nonzero(self, caplog):
        state = ExplorationState()
        state.gen_count_rewritten = 3

        with caplog.at_level(logging.INFO, logger="ct.engine"):
            emit_run_summary(state)

        records = [r for r in caplog.records if r.name == "ct.engine"]
        assert len(records) == 1
        assert records[0].levelno == logging.INFO
        assert "rewrites" in records[0].getMessage().lower()

    # TDD path step: zero-counter-runs-suppress-line
    def test_suppresses_the_summary_line_when_every_counter_is_zero(self, caplog):
        state = ExplorationState()

        with caplog.at_level(logging.INFO, logger="ct.engine"):
            emit_run_summary(state)

        assert [r for r in caplog.records if r.name == "ct.engine"] == []

    # TDD path step: summary-includes-firing-and-skip
    def test_summary_line_includes_both_firing_and_skip_counters(self, caplog):
        state = ExplorationState()
        state.gen_count_rewritten = 2
        state.gen_count_skipped_symbolic_sub = 1

        with caplog.at_level(logging.INFO, logger="ct.engine"):
            emit_run_summary(state)

        records = [r for r in caplog.records if r.name == "ct.engine"]
        assert len(records) == 1
        message = records[0].getMessage()
        assert "gen_count_rewritten=2" in message
        assert "gen_count_skipped_symbolic_sub=1" in message

    def test_emission_uses_lazy_percent_formatting(self, caplog):
        # Logging discipline: %-formatting deferred to handler; the
        # log record carries args separately from msg so emission stays
        # cheap when the logger level filters the line out.
        state = ExplorationState()
        state.gen_membership_rewritten = 1

        with caplog.at_level(logging.INFO, logger="ct.engine"):
            emit_run_summary(state)

        record = next(r for r in caplog.records if r.name == "ct.engine")
        assert record.args is not None
        assert "%s" in record.msg or "%" in record.msg


class _Result:
    """Minimal stand-in exposing the ``inputs_generated`` attribute that
    ``emit_target_errors`` reads (duck-typed like ``emit_run_summary``)."""

    def __init__(self, records: list[InputRecord]):
        self.inputs_generated = tuple(records)


def _rec(
    outcome: Outcome,
    *,
    error: str | None = None,
    args: dict | None = None,
    provenance: Provenance = Provenance.SOLVER,
) -> InputRecord:
    return InputRecord(
        args=args or {},
        provenance=provenance,
        outcome=outcome,
        new_lines=frozenset(),
        error=error,
    )


class TestTargetErrorEmission:
    """``emit_target_errors`` logs one INFO line per crashing input.

    Parent-side emission from the returned records is what makes a
    triggered error visible in ``benchmark.log`` — the engine's own
    in-loop DEBUG line runs in a child subprocess and never gets there.
    Each line names the exception and the triggering input.
    """

    def test_emits_one_info_line_per_target_error_record(self, caplog):
        result = _Result([_rec(Outcome.TARGET_ERROR, error="AssertionError: x>10", args={"x": 11})])

        with caplog.at_level(logging.INFO, logger="ct.engine"):
            emit_target_errors(result)

        records = [r for r in caplog.records if r.name == "ct.engine"]
        assert len(records) == 1
        assert records[0].levelno == logging.INFO
        message = records[0].getMessage()
        assert "AssertionError: x>10" in message
        assert "11" in message  # the triggering input surfaces too

    def test_no_line_for_clean_or_timeout_records(self, caplog):
        result = _Result(
            [
                _rec(Outcome.COVERED_NEW),
                _rec(Outcome.NO_GAIN),
                _rec(Outcome.TIMEOUT, error="timeout: deadline exceeded"),
            ]
        )

        with caplog.at_level(logging.INFO, logger="ct.engine"):
            emit_target_errors(result)

        assert [r for r in caplog.records if r.name == "ct.engine"] == []

    def test_emits_a_line_for_each_target_error(self, caplog):
        result = _Result(
            [
                _rec(Outcome.TARGET_ERROR, error="ValueError: a"),
                _rec(Outcome.COVERED_NEW),
                _rec(Outcome.TARGET_ERROR, error="KeyError: b"),
            ]
        )

        with caplog.at_level(logging.INFO, logger="ct.engine"):
            emit_target_errors(result)

        records = [r for r in caplog.records if r.name == "ct.engine"]
        assert len(records) == 2
        joined = " ".join(r.getMessage() for r in records)
        assert "ValueError: a" in joined
        assert "KeyError: b" in joined

    def test_uses_lazy_percent_formatting(self, caplog):
        result = _Result([_rec(Outcome.TARGET_ERROR, error="ValueError: x")])

        with caplog.at_level(logging.INFO, logger="ct.engine"):
            emit_target_errors(result)

        record = next(r for r in caplog.records if r.name == "ct.engine")
        assert record.args is not None
        assert "%" in record.msg
