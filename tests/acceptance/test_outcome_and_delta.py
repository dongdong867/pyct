"""Acceptance tests: input record outcome + mechanical coverage delta.

The engine attaches an Outcome and a per-iteration ``new_lines`` delta to
every executed input. Outcome classifies the iteration result
(COVERED_NEW / NO_GAIN / TARGET_ERROR / TIMEOUT). ``new_lines`` carries
the mechanical delta of newly observed lines and is independent of
outcome — TARGET_ERROR / TIMEOUT records may still carry non-empty
``new_lines`` for lines traced before the failure. The result also
exposes ``pre_cover_lines`` (lines already covered before the
exploration loop ran) so the invariant ``∪ new_lines == executed_lines −
pre_cover_lines`` is computable from the JSON alone.
"""

from __future__ import annotations

from typing import Any

from pyct.config.execution import ExecutionConfig
from pyct.engine.coverage_scope import CoverageScope
from pyct.engine.engine import Engine
from pyct.engine.function_inspector import inspect_target
from pyct.engine.types import Outcome


def _two_branch(x: int) -> int:
    """One branch — exercises both arms via solver flip."""
    if x > 10:
        return 1
    return 0


def _crash_after_branch(x: int) -> int:
    """Covers a branch line then raises — TARGET_ERROR with non-empty new_lines."""
    if x > 0:
        raise ValueError("bad")
    return -x


def _spin(x: int) -> int:
    """Tight loop — pairs with a near-zero seed_soft_timeout to force TIMEOUT."""
    y = x
    while True:
        y += 1
    return y  # unreachable


class _SeedSource:
    """Plugin returning canned seeds via on_seed_request."""

    name = "seed_source"
    priority = 100

    def __init__(self, seeds: list[dict[str, Any]]) -> None:
        self._seeds = seeds

    def on_seed_request(self, ctx: Any) -> list[dict[str, Any]]:
        return [dict(s) for s in self._seeds]


class TestOutcomeClassification:
    """Outcome reflects iteration result: gain, no gain, error, timeout."""

    def test_initial_seed_covering_new_lines_is_covered_new(self):
        """
        Given a target with one branch
          And run from a fresh seed that traces previously unseen lines
        When exploration completes
        Then the first record's outcome is COVERED_NEW
        """
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        result = engine.explore(_two_branch, {"x": 0})
        assert result.inputs_generated[0].outcome is Outcome.COVERED_NEW

    def test_plugin_duplicate_coverage_seed_is_no_gain(self):
        """
        Given a branchy target where one arm leaves coverage incomplete
          And a plugin returning a same-arm seed (covers the lines the
              initial seed already traced)
        When both iterations run
        Then the plugin-seeded record carries outcome NO_GAIN and empty new_lines
        """
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        # Both initial x=0 and plugin x=-5 take the else arm — same line set,
        # so the plugin seed must classify as NO_GAIN. Solver later flips
        # the branch to cover the if arm, but that's a separate record.
        engine.register(_SeedSource(seeds=[{"x": -5}]))
        result = engine.explore(_two_branch, {"x": 0})

        assert len(result.inputs_generated) >= 2
        assert result.inputs_generated[0].outcome is Outcome.COVERED_NEW
        plugin_record = next(r for r in result.inputs_generated if r.args == {"x": -5})
        assert plugin_record.outcome is Outcome.NO_GAIN
        assert plugin_record.new_lines == frozenset()
        assert plugin_record.error is None

    def test_target_raise_classified_as_target_error(self):
        """
        Given a target that raises before returning
        When exploration completes
        Then the first record's outcome is TARGET_ERROR
          And error is the ``"{Type}: {msg}"`` form
        """
        config = ExecutionConfig(max_iterations=5, timeout_seconds=5.0)
        engine = Engine(config)
        result = engine.explore(_crash_after_branch, {"x": 5})

        assert result.inputs_generated[0].outcome is Outcome.TARGET_ERROR
        assert result.inputs_generated[0].error == "ValueError: bad"

    def test_target_error_record_keeps_new_lines_traced_before_crash(self):
        """
        Given a target that traces lines then raises
        When the iteration ends in TARGET_ERROR
        Then new_lines is non-empty for that record
        """
        config = ExecutionConfig(max_iterations=5, timeout_seconds=5.0)
        engine = Engine(config)
        result = engine.explore(_crash_after_branch, {"x": 5})

        record = result.inputs_generated[0]
        assert record.outcome is Outcome.TARGET_ERROR
        # Lines hit before raise ⇒ tracer recorded at least one body line.
        assert record.new_lines != frozenset()

    def test_timeout_in_process_classified_as_timeout(self):
        """
        Given a tight-loop target
          And seed_soft_timeout near zero so the deadline fires immediately
        When the in-process tracer raises TimeoutError
        Then the record's outcome is TIMEOUT
          And error begins with ``"timeout:"``
        """
        config = ExecutionConfig(
            max_iterations=2,
            timeout_seconds=5.0,
            seed_soft_timeout=0.0001,
        )
        engine = Engine(config)
        result = engine.explore(_spin, {"x": 0})

        assert result.inputs_generated[0].outcome is Outcome.TIMEOUT
        assert result.inputs_generated[0].error is not None
        assert result.inputs_generated[0].error.startswith("timeout:")

    def test_clean_outcomes_have_no_error_field(self):
        """
        Given a fully-clean exploration (no raise, no timeout)
        When records are inspected
        Then every record's error field is None
        """
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        result = engine.explore(_two_branch, {"x": 0})

        for record in result.inputs_generated:
            if record.outcome in (Outcome.COVERED_NEW, Outcome.NO_GAIN):
                assert record.error is None


class TestNewLinesDelta:
    """``new_lines`` reflects the mechanical observed-lines delta per iter."""

    def test_new_lines_is_strict_subset_of_executed_lines(self):
        """
        Given a successful exploration
        When records are inspected
        Then every record.new_lines is a subset of result.executed_lines
        """
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        result = engine.explore(_two_branch, {"x": 0})

        for record in result.inputs_generated:
            assert record.new_lines.issubset(result.executed_lines)

    def test_new_lines_are_pairwise_disjoint(self):
        """
        Given multi-iteration exploration
        When records are inspected
        Then no line appears in two records' new_lines
          (Each line is "first observed" by exactly one iteration.)
        """
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        result = engine.explore(_two_branch, {"x": 0})

        seen: set[int] = set()
        for record in result.inputs_generated:
            assert seen.isdisjoint(record.new_lines), (
                f"line(s) {seen & record.new_lines} reported in two records' new_lines"
            )
            seen |= record.new_lines


class TestPreCoverLinesSnapshot:
    """``result.pre_cover_lines`` snapshots covered_lines pre-loop."""

    def test_pre_cover_lines_is_frozenset(self):
        """
        Given any successful exploration
        When result is built
        Then pre_cover_lines is a frozenset of ints
        """
        config = ExecutionConfig(max_iterations=5, timeout_seconds=5.0)
        engine = Engine(config)
        result = engine.explore(_two_branch, {"x": 0})

        assert isinstance(result.pre_cover_lines, frozenset)

    def test_pre_cover_lines_disjoint_from_executed_lines(self):
        """
        Given the engine's pre-cover semantics (def-header lines etc. that
        the tracer never fires on)
        When the run completes
        Then pre_cover_lines and executed_lines are disjoint
          (Pre-covered lines, by definition, were never tracer-observed.)
        """
        config = ExecutionConfig(max_iterations=5, timeout_seconds=5.0)
        engine = Engine(config)
        result = engine.explore(_two_branch, {"x": 0})

        assert result.pre_cover_lines.isdisjoint(result.executed_lines)

    def test_pre_cover_lines_reflects_explicit_scope_pre_covered(self):
        """
        Given a CoverageScope with explicit pre_covered lines
          And those lines are a subset of executable_lines (so they enter
              the narrow covered_lines view)
        When exploration runs
        Then pre_cover_lines on the result equals the scope's pre_covered set
        """
        target_file, func_lines, def_line = inspect_target(_two_branch)
        # Pick one body line as "pre-covered" for the test — the engine
        # must snapshot it before the loop runs.
        pre_pick = frozenset({next(iter(func_lines))})
        scope = CoverageScope.for_file(target_file, func_lines, pre_covered=pre_pick)
        config = ExecutionConfig(max_iterations=5, timeout_seconds=5.0, scope=scope)
        engine = Engine(config)
        result = engine.explore(_two_branch, {"x": 0})

        assert pre_pick.issubset(result.pre_cover_lines)


class TestCoverageDeltaInvariant:
    """``∪ record.new_lines == executed_lines − pre_cover_lines``."""

    def test_invariant_holds_on_branchy_target(self):
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        result = engine.explore(_two_branch, {"x": 0})

        union = frozenset().union(*(r.new_lines for r in result.inputs_generated))
        assert union == result.executed_lines - result.pre_cover_lines

    def test_invariant_holds_when_no_gain_records_present(self):
        config = ExecutionConfig(max_iterations=10, timeout_seconds=5.0)
        engine = Engine(config)
        engine.register(_SeedSource(seeds=[{"x": -5}]))  # duplicate-coverage seed
        result = engine.explore(_two_branch, {"x": 0})

        # Make sure at least one NO_GAIN record participated, otherwise this
        # test reduces to the branchy-target case.
        assert any(r.outcome is Outcome.NO_GAIN for r in result.inputs_generated)
        union = frozenset().union(*(r.new_lines for r in result.inputs_generated))
        assert union == result.executed_lines - result.pre_cover_lines

    def test_invariant_holds_when_target_error_present(self):
        config = ExecutionConfig(max_iterations=5, timeout_seconds=5.0)
        engine = Engine(config)
        result = engine.explore(_crash_after_branch, {"x": 5})

        union = frozenset().union(*(r.new_lines for r in result.inputs_generated))
        assert union == result.executed_lines - result.pre_cover_lines
