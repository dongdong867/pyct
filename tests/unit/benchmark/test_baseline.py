"""Baseline data model + pure measurement function.

Frozen baselines give library/realworld targets a shared, reviewable
denominator across runners. Tests cover:

- Happy: full / partial hits, def-line backfill within a scope.
- Edge: no hits, hits outside scope, multi-scope no-cross-leak,
  empty-scope baseline.
- Error: loading a missing baseline file.
"""

from __future__ import annotations

import pytest
from tools.benchmark.baseline import (
    Baseline,
    FunctionScope,
    measure_against_baseline,
)


def _make_baseline(*scopes: FunctionScope, target: str = "t") -> Baseline:
    return Baseline(
        target=target,
        scopes=tuple(scopes),
        generated_at="2026-04-17T00:00:00",
        generator_version="1",
    )


# ── Data model ────────────────────────────────────────────────────


def test_baseline_total_lines_sums_across_scopes():
    baseline = _make_baseline(
        FunctionScope("a.py", 1, 5, (1, 2, 3)),
        FunctionScope("b.py", 10, 20, (10, 11)),
    )

    assert baseline.total_lines == 5


def test_baseline_total_lines_zero_when_no_scopes():
    assert _make_baseline().total_lines == 0


def test_baseline_json_round_trip(tmp_path):
    original = _make_baseline(
        FunctionScope("yaml/__init__.py", 40, 50, (40, 42, 43)),
        FunctionScope("yaml/loader.py", 10, 30, (10, 11, 12, 15)),
        target="yaml.safe_load",
    )
    path = tmp_path / "baseline.json"

    original.to_json(path)
    loaded = Baseline.from_json(path)

    assert loaded == original


def test_baseline_from_json_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        Baseline.from_json(tmp_path / "missing.json")


# ── Measurement — happy paths ─────────────────────────────────────


def test_measure_full_hits_is_100_percent():
    baseline = _make_baseline(FunctionScope("a.py", 1, 10, (1, 2, 3, 5)))
    hits = {"a.py": {1, 2, 3, 5}}

    result = measure_against_baseline(hits, baseline)

    assert result.total_lines == 4
    assert result.executed_lines == 4
    assert result.coverage_percent == 100.0


def test_measure_partial_hits_backfills_def_lines_within_scope():
    # Body hit at 5 and 7; def (1) and pre-body (3) not marked by coverage.py
    # but must be counted as hit because the function executed.
    baseline = _make_baseline(FunctionScope("a.py", 1, 10, (1, 3, 5, 7)))
    hits = {"a.py": {5, 7}}

    result = measure_against_baseline(hits, baseline)

    assert result.executed_lines == 4  # {1, 3, 5, 7} after backfill
    assert result.coverage_percent == 100.0


# ── Measurement — edge cases ──────────────────────────────────────


def test_measure_no_hits_is_zero_percent():
    baseline = _make_baseline(FunctionScope("a.py", 1, 10, (1, 2, 3, 5)))

    result = measure_against_baseline({}, baseline)

    assert result.total_lines == 4
    assert result.executed_lines == 0
    assert result.coverage_percent == 0.0


def test_measure_backfill_does_not_cross_scope_boundaries():
    # Two scopes — a hit in one must not backfill lines in the other.
    baseline = _make_baseline(
        FunctionScope("a.py", 1, 10, (1, 3, 5)),
        FunctionScope("b.py", 20, 30, (20, 22, 25)),
    )
    hits = {"a.py": {5}}  # last line of fn1; fn2 untouched

    result = measure_against_baseline(hits, baseline)

    # fn1 backfills def/pre-body → {1, 3, 5}; fn2 stays at 0
    assert result.total_lines == 6
    assert result.executed_lines == 3


def test_measure_ignores_hits_outside_baseline_scope():
    baseline = _make_baseline(FunctionScope("a.py", 1, 10, (1, 3, 5)))
    hits = {"a.py": {5, 99, 100}, "unrelated.py": {1, 2}}

    result = measure_against_baseline(hits, baseline)

    # Only in-scope line 5 is hit; backfill yields {1, 3, 5}
    assert result.total_lines == 3
    assert result.executed_lines == 3


def test_measure_empty_baseline_returns_zero_without_division_error():
    result = measure_against_baseline({}, _make_baseline())

    assert result.total_lines == 0
    assert result.executed_lines == 0
    assert result.coverage_percent == 0.0


def test_measure_backfill_only_applies_when_some_body_line_hit():
    # If NO line in a scope is hit, the def line is not retroactively covered.
    baseline = _make_baseline(FunctionScope("a.py", 1, 10, (1, 3, 5)))
    hits = {"a.py": set()}  # empty — explicitly no hits

    result = measure_against_baseline(hits, baseline)

    assert result.executed_lines == 0


# ── Line-number reporting ─────────────────────────────────────────


def test_measure_populates_executed_line_numbers_as_sorted_union():
    # Two scopes in two files each with partial hits. The flat
    # executed_line_numbers list must be the sorted union of what was
    # covered (including def-line backfill) so downstream diff tools
    # can compare runners line-by-line.
    baseline = _make_baseline(
        FunctionScope("a.py", 1, 10, (1, 3, 5, 7)),
        FunctionScope("b.py", 20, 30, (20, 22, 25)),
    )
    hits = {"a.py": {5, 7}, "b.py": {25}}

    result = measure_against_baseline(hits, baseline)

    # a.py: {5, 7} hit + backfill {1, 3} = {1, 3, 5, 7}
    # b.py: {25} hit + backfill {20, 22} = {20, 22, 25}
    assert result.executed_line_numbers == [1, 3, 5, 7, 20, 22, 25]


def test_measure_populates_executed_by_file_dict():
    # Multi-scope baseline — callers need per-file context so line
    # numbers aren't ambiguous across files.
    baseline = _make_baseline(
        FunctionScope("a.py", 1, 10, (1, 3, 5, 7)),
        FunctionScope("b.py", 20, 30, (20, 22, 25)),
    )
    hits = {"a.py": {5, 7}, "b.py": {25}}

    result = measure_against_baseline(hits, baseline)

    assert result.executed_by_file == {
        "a.py": [1, 3, 5, 7],
        "b.py": [20, 22, 25],
    }


def test_measure_executed_by_file_omits_files_with_zero_coverage():
    # A scope with no hits should not contribute an empty list — keeps
    # the output focused on what was actually touched.
    baseline = _make_baseline(
        FunctionScope("a.py", 1, 10, (1, 3, 5)),
        FunctionScope("b.py", 20, 30, (20, 22, 25)),
    )
    hits = {"a.py": {5}}  # b.py untouched

    result = measure_against_baseline(hits, baseline)

    assert result.executed_by_file == {"a.py": [1, 3, 5]}


def test_measure_aggregates_multiple_scopes_in_same_file():
    # Two scopes in one file → executed_by_file collapses them under
    # the file key, sorted.
    baseline = _make_baseline(
        FunctionScope("a.py", 1, 10, (1, 3, 5)),
        FunctionScope("a.py", 20, 30, (20, 22, 25)),
    )
    hits = {"a.py": {5, 25}}

    result = measure_against_baseline(hits, baseline)

    assert result.executed_by_file == {"a.py": [1, 3, 5, 20, 22, 25]}
    assert result.executed_line_numbers == [1, 3, 5, 20, 22, 25]
