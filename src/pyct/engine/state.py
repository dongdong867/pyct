"""Internal exploration state — mutable, owned by the engine."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from pyct.engine.types import InputRecord

if TYPE_CHECKING:
    from pyct.engine.coverage_tracker import CoverageTracker


@dataclass
class ExplorationState:
    """Mutable state for an in-progress exploration run.

    This is engine-internal. Plugins receive a read-only snapshot via
    EngineContext, not this object directly. The engine updates this
    state in place as exploration progresses.

    Attributes:
        iteration: Current iteration count, starting at zero.
        constraint_pool: Path constraints awaiting exploration.
        covered_lines: Set of source line numbers hit so far, including
            synthetic pre-covered headers (used for plateau detection
            and coverage_percent reporting during exploration). This is
            the *narrow* view — target-file only — for plugin snapshots
            and legacy callers.
        observed_lines: Subset of covered_lines that the tracer actually
            saw fire — excludes pre-covered. This is what gets reported
            to callers as ``executed_lines`` so downstream def-header
            backfill heuristics work correctly. Narrow view.
        total_lines: Total executable lines in the target function
            (narrow view). ``scope_total_lines`` is the wide counterpart.
        records: History of executed inputs as InputRecord instances —
            each carries provenance, outcome, mechanical coverage delta,
            and exception text. The next-input dedup check, plugin-context
            ``inputs_tried`` snapshot, and ``paths_explored`` count all
            derive from this list.
        start_time: Wall-clock start time (from time.monotonic()).
        last_coverage_change_iteration: Iteration number when coverage
            last increased. Used to detect plateaus.
        terminated: True once the engine has stopped exploring.
        termination_reason: Human-readable reason for termination, or
            None if still running.
        seed_phase: True while the engine is still replaying pre-supplied
            or plateau-requested seeds. While True, ``max_iterations``
            and ``timeout_seconds`` do not apply — only the per-seed
            soft timeout bounds each iteration. Flipped to False in
            ``_next_input`` when the input queue first drains, and
            re-enabled by ``_handle_plateau`` when new plugin seeds are
            appended to the queue.
        pre_cover_lines: Snapshot of ``covered_lines`` taken before the
            exploration loop's first iteration. Captures lines the
            tracker reports as covered without the engine having executed
            them (e.g., scope-level pre-covered ``def`` headers). Used as
            the baseline for the coverage-delta invariant
            ``∪ record.new_lines == executed_lines − pre_cover_lines``,
            which lets a result consumer reconstruct per-input deltas
            from the JSON alone.
        coverage_at_last_plateau: Wide scope_observed_count recorded at
            the moment the engine last dispatched ``on_coverage_plateau``.
            Set by ``_handle_plateau``, cleared by ``_check_plateau_outcome``
            once the plateau seeds have drained and the engine can
            measure whether they improved coverage.
        plateau_failure_count: Consecutive plateau dispatches whose
            seeds failed to improve coverage. Resets to zero on any
            successful recovery; drives the silencing policy that
            terminates exploration with ``plateau_exhausted`` once the
            count reaches ``ExecutionConfig.max_stale_llm_attempts``.
        tracker: The engine's CoverageTracker. Optional for backward
            compatibility with tests that construct state standalone;
            when None, the ``scope_*`` views return zero. When set, the
            wide views forward to the tracker's scope-spanning counters.
        gen_unsat: Solver-returned-UNSAT count over the run. Bumped at
            every solver call that proves the constraint unreachable;
            no input is produced for these calls.
        gen_unknown: Solver-returned-UNKNOWN-or-ERROR count over the run.
            Counted raw — every UNKNOWN/ERROR bumps this counter even
            when a plugin's ``on_constraint_unknown`` resolver later
            supplies an alternate input. Resolution is orthogonal: the
            resolved record carries provenance ``PLUGIN_UNKNOWN`` so the
            two facts can be cross-referenced from the result alone.
        gen_substr_let_bound: ``str.substr`` let-binding emission count
            over the run. Bumped inside ``_build_substr_expression``
            every time the helper wraps its output in an SMT ``let`` so
            start/end bounds are named once and referenced by name,
            avoiding duplicate evaluation of the start expression in the
            length term. Concrete bounds skip their binding and inline
            directly inside the let body; the counter still bumps once
            per emission regardless of how many args were bound.
        gen_count_rewritten: ``str.count`` rewrite-fire count over the
            run. Bumped inside ``constraint_optimizer.optimize`` every
            time a ``count(sub) == k`` predicate with literal ``sub`` and
            literal ``k`` is substituted out of the solver-hostile
            ``str.replace_all + div`` shape — into ``(not (str.contains
            region sub))`` for ``k == 0`` or a ``k``-fold chained
            ``str.indexof`` form for ``k >= 1``. Bumps once per
            substitution site so the counter equals the number of
            predicates the rule simplified.
        gen_count_skipped_symbolic_sub: ``str.count`` rewrite-skip count
            for symbolic-sub fallbacks over the run. Bumped inside
            ``constraint_optimizer.optimize`` whenever a ``count``
            predicate's ``sub`` argument is symbolic (not a literal
            string) — the rule cannot fire and the baseline
            ``replace_all + div`` emission is preserved unchanged.
            Distinct from ``gen_count_rewritten`` so telemetry can show
            both the fire rate and the symbolic-sub miss rate side by
            side.
        gen_membership_rewritten: literal-container membership
            rewrite-fire count over the run. Bumped inside
            ``ConcolicCompareRewriter.visit_Compare`` every time an
            ``In`` / ``NotIn`` Compare whose comparator is a literal
            ``Set`` / ``Tuple`` / ``List`` / ``Dict`` is expanded into
            a ``BoolOp(Or, [Compare(Eq), …])`` (or ``BoolOp(And,
            [Compare(NotEq), …])``) form so each element becomes its
            own flippable disjunct. Bumps once per Compare rewritten;
            the empty-container collapse to ``Constant(False)`` and the
            single-element collapse to a bare ``Compare(Eq)`` still
            count as one fire each.
        gen_membership_skipped_non_literal: literal-container membership
            rewrite-skip count for non-literal fallbacks over the run.
            Bumped inside ``ConcolicCompareRewriter.visit_Compare``
            whenever a Compare's comparator is not one of the supported
            literal container nodes (e.g. a ``Name``) or any element of
            the literal container is itself non-literal — the rewrite
            cannot fire and the Compare is returned unchanged so
            baseline emission semantics are preserved bit-for-bit.
            Distinct from ``gen_membership_rewritten`` so telemetry can
            show both the fire rate and the non-literal miss rate side
            by side.
        gen_str_to_int_singleton_rewritten: ``int(ConcolicStr)``
            singleton-char rewrite-fire count over the run. Bumped
            inside ``ConcolicStr.to_int`` every time the helper is
            invoked on a single-character string and emits symbolic
            tracking that links the resulting ``ConcolicInt`` back to
            the originating char. Tags both the direct ``int(s[i])``
            call shape and the ``map(int, x)`` expansion the AST
            rewriter produces, so a single counter covers per-char
            int routing regardless of the surface syntax.
        harness_error: ``wrap_arguments`` failure count over the run.
            Bumped inside ``_run_iteration`` when Concolic construction
            raises before the target is called. The iteration still
            appends a record (carrying the wrap error and TARGET_ERROR
            outcome) so callers can see which seed failed.
    """

    iteration: int = 0
    constraint_pool: list[Any] = field(default_factory=list)
    covered_lines: set[int] = field(default_factory=set)
    observed_lines: set[int] = field(default_factory=set)
    total_lines: int = 0
    records: list[InputRecord] = field(default_factory=list)
    start_time: float = 0.0
    last_coverage_change_iteration: int = 0
    terminated: bool = False
    termination_reason: str | None = None
    seed_phase: bool = True
    pre_cover_lines: frozenset[int] = field(default_factory=frozenset)
    coverage_at_last_plateau: int | None = None
    plateau_failure_count: int = 0
    tracker: CoverageTracker | None = None
    gen_unsat: int = 0
    gen_unknown: int = 0
    gen_substr_let_bound: int = 0
    gen_count_rewritten: int = 0
    gen_count_skipped_symbolic_sub: int = 0
    gen_membership_rewritten: int = 0
    gen_membership_skipped_non_literal: int = 0
    gen_str_to_int_singleton_rewritten: int = 0
    harness_error: int = 0

    def coverage_percent(self) -> float:
        """Return narrow coverage as a 0-100 percentage (target file only)."""
        if self.total_lines == 0:
            return 0.0
        return 100.0 * len(self.covered_lines) / self.total_lines

    def paths_explored(self) -> int:
        """Return the number of distinct inputs that have been tried."""
        return len(self.records)

    def has_seen_args(self, args: dict[str, Any]) -> bool:
        """Return True if ``args`` matches any prior record's args dict."""
        return any(record.args == args for record in self.records)

    def elapsed_seconds(self) -> float:
        """Return wall-clock seconds since start_time was set."""
        return time.monotonic() - self.start_time

    # ── Wide-scope views (forward to the optional tracker) ────────────
    #
    # These let the engine reason about scope-spanning coverage for
    # termination and plateau decisions without altering the narrow
    # fields that plugin snapshots expose.

    @property
    def scope_total_lines(self) -> int:
        """Sum of executable lines across all scope files (wide)."""
        return self.tracker.total_lines if self.tracker is not None else 0

    @property
    def scope_observed_count(self) -> int:
        """Tracer-observed line count across all scope files (wide)."""
        return self.tracker.observed_count if self.tracker is not None else 0

    @property
    def scope_covered_count(self) -> int:
        """Observed ∪ pre-covered line count across all scope files (wide)."""
        return self.tracker.covered_count if self.tracker is not None else 0

    def scope_coverage_percent(self) -> float:
        """Wide coverage ratio as a 0-100 percentage."""
        return self.tracker.coverage_percent if self.tracker is not None else 0.0
