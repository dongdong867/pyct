"""Run-end telemetry emission for rewrite counter visibility."""

from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("ct.engine")

# Rewrite-classification counters tracked through the run. Order is the
# canonical reading order for ``benchmark.log``: firing/skip pairs sit
# adjacent so a reader can scan a class's fire rate against its skip rate
# without hunting the line.
_REWRITE_COUNTERS: tuple[str, ...] = (
    "gen_substr_let_bound",
    "gen_count_rewritten",
    "gen_count_skipped_symbolic_sub",
    "gen_membership_rewritten",
    "gen_membership_skipped_non_literal",
    "gen_str_to_int_singleton_rewritten",
    "gen_case_fold_rewritten",
    "gen_case_fold_skipped_non_ascii",
    "gen_chain_deprioritized",
)


def emit_run_summary(source: Any) -> None:
    """Log one INFO line summarizing non-zero rewrite counters for the run.

    ``source`` is any object exposing the rewrite-class counter attributes
    by name — ``ExplorationState`` (in-engine), ``ExplorationResult``, or
    ``RunConcolicResult`` (parent-side after an isolated run all qualify.
    Emission is suppressed when every tracked counter is zero so targets
    exercising no rewrites stay quiet in ``benchmark.log``.
    """
    counts = [(name, getattr(source, name)) for name in _REWRITE_COUNTERS]
    if all(value == 0 for _, value in counts):
        return
    body = " ".join(f"{name}={value}" for name, value in counts if value > 0)
    log.info("rewrites: %s", body)
