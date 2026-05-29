"""Acceptance test for rewrite-telemetry log emission (Task 7)."""

import logging


# telemetry-rewrite-visible:
#   Given the benchmark suite ran on a realworld target that fired each
#     rewrite class and triggered at least one skip condition
#   When the user reads `benchmark.log` for the run
#   Then the log shows a line per target/runner with non-zero counts for
#     each fired rewrite class
#     And the log line carries non-zero counts for each skip class that
#     triggered
#     And every firing counter and skip counter is distinguishable in
#     the log line
def test_telemetry_summary_line_lists_fired_and_skipped_rewrites(caplog):
    """
    Given a target whose exploration fires multiple rewrite classes and
      triggers at least one skip class
    When the engine completes the run
    Then a single INFO-level log line on ``ct.engine`` summarizes the run
      And the line carries the count for every firing counter that fired
      And the line carries the count for every skip counter that triggered
      And each counter is identifiable by its own attribute name in the
      line so firing and skip counters do not collide
    """
    from pyct import run_concolic
    from tests.acceptance.fixtures.strings.multi_rewrite import multi_rewrite

    with caplog.at_level(logging.INFO, logger="ct.engine"):
        result = run_concolic(
            target=multi_rewrite,
            initial_args={"text": "", "marker": ""},
        )

    assert result.success

    # Sanity: the chosen fixture actually exercises both kinds of
    # counter so the assertions below are meaningful. If this ever
    # regresses, the AC's premise is gone and the test should fail
    # loudly here rather than silently passing on the no-counter line.
    fired_any = (
        result.gen_count_rewritten > 0
        or result.gen_case_fold_rewritten > 0
        or result.gen_membership_rewritten > 0
    )
    skipped_any = (
        result.gen_count_skipped_symbolic_sub > 0
        or result.gen_case_fold_skipped_non_ascii > 0
        or result.gen_membership_skipped_non_literal > 0
    )
    assert fired_any, "fixture should fire at least one rewrite class"
    assert skipped_any, "fixture should trigger at least one skip class"

    summary_records = [
        r
        for r in caplog.records
        if r.name == "ct.engine"
        and r.levelno == logging.INFO
        and "rewrites" in r.getMessage().lower()
    ]
    assert len(summary_records) == 1, (
        "Expected exactly one rewrite-telemetry summary line; got "
        f"{len(summary_records)}: {[r.getMessage() for r in summary_records]}"
    )
    line = summary_records[0].getMessage()

    firing_counters = {
        "gen_substr_let_bound": result.gen_substr_let_bound,
        "gen_count_rewritten": result.gen_count_rewritten,
        "gen_membership_rewritten": result.gen_membership_rewritten,
        "gen_str_to_int_singleton_rewritten": result.gen_str_to_int_singleton_rewritten,
        "gen_case_fold_rewritten": result.gen_case_fold_rewritten,
        "gen_chain_deprioritized": result.gen_chain_deprioritized,
    }
    skip_counters = {
        "gen_count_skipped_symbolic_sub": result.gen_count_skipped_symbolic_sub,
        "gen_membership_skipped_non_literal": result.gen_membership_skipped_non_literal,
        "gen_case_fold_skipped_non_ascii": result.gen_case_fold_skipped_non_ascii,
    }

    for name, value in firing_counters.items():
        if value > 0:
            assert f"{name}={value}" in line, (
                f"Expected firing counter {name}={value} in summary line; "
                f"got {line!r}"
            )

    for name, value in skip_counters.items():
        if value > 0:
            assert f"{name}={value}" in line, (
                f"Expected skip counter {name}={value} in summary line; "
                f"got {line!r}"
            )
