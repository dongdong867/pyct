"""Thin wrapper that turns per-run scope lists into a finished :class:`Baseline`.

Composes normalize → merge → stamp metadata. The individual steps are
covered elsewhere; these tests pin the contract of the wrapper itself
(target name propagated, timestamp formatted, version tagged, paths
normalized before merge so dedupe works on the portable key).
"""

from __future__ import annotations

from datetime import datetime

from tools.benchmark.baseline import (
    BASELINE_SCHEMA_VERSION,
    FunctionScope,
    build_baseline,
)

_NOW = datetime(2026, 4, 17, 12, 0, 0)


def _abs(pkg_rel: str) -> str:
    return f"/v/lib/python3.12/site-packages/{pkg_rel}"


def test_build_baseline_normalizes_absolute_paths():
    run_scopes = [
        FunctionScope(_abs("yaml/__init__.py"), 1, 5, (1, 2, 3)),
    ]

    baseline = build_baseline("yaml.safe_load", [run_scopes], _NOW)

    assert baseline.scopes[0].file == "yaml/__init__.py"


def test_build_baseline_dedupes_identical_scopes_across_runs():
    scope = FunctionScope(_abs("yaml/__init__.py"), 1, 5, (1, 2, 3))

    baseline = build_baseline("yaml.safe_load", [[scope], [scope]], _NOW)

    assert len(baseline.scopes) == 1


def test_build_baseline_unions_distinct_scopes_across_runs():
    # Runner 1 entered func A; runner 2 entered func B. Both should
    # appear in the final baseline — this is the "union across runners"
    # contract that makes the baseline a shared denominator.
    scope_a = FunctionScope(_abs("yaml/__init__.py"), 1, 5, (1, 2, 3))
    scope_b = FunctionScope(_abs("yaml/loader.py"), 10, 20, (10, 11))

    baseline = build_baseline("yaml.safe_load", [[scope_a], [scope_b]], _NOW)

    assert {s.file for s in baseline.scopes} == {
        "yaml/__init__.py",
        "yaml/loader.py",
    }


def test_build_baseline_drops_scopes_outside_site_packages():
    in_scope = FunctionScope(_abs("yaml/__init__.py"), 1, 5, (1, 2, 3))
    out_of_scope = FunctionScope("/Users/dong/dev/pyct/src/pyct/engine.py", 1, 5, (1, 2, 3))

    baseline = build_baseline("yaml.safe_load", [[in_scope, out_of_scope]], _NOW)

    assert len(baseline.scopes) == 1
    assert baseline.scopes[0].file == "yaml/__init__.py"


def test_build_baseline_stamps_target_timestamp_and_version():
    baseline = build_baseline("yaml.safe_load", [], _NOW)

    assert baseline.target == "yaml.safe_load"
    assert baseline.generated_at == "2026-04-17T12:00:00"
    assert baseline.generator_version == BASELINE_SCHEMA_VERSION


def test_build_baseline_handles_no_runs():
    baseline = build_baseline("yaml.safe_load", [], _NOW)

    assert baseline.scopes == ()
    assert baseline.total_lines == 0
