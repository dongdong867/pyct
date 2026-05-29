"""Unit tests for rewrite-telemetry summary emission at run end."""

import logging

from pyct.engine.state import ExplorationState
from pyct.engine.telemetry import emit_run_summary


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
