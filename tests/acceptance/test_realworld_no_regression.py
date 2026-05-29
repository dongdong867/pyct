"""Acceptance test for no-baseline-regression AC.

Reads two benchmark results.json artifacts (baseline + latest) produced by
the realworld benchmark suite, intersects on the five Mode-2 targets called
out in the smt-constraint-encoding-fixes spec, and asserts per-target:

- pure_concolic coverage (post) >= pure_concolic coverage (baseline)
- |concolic_llm coverage (post) - concolic_llm coverage (baseline)| <= 5 pp
- wall-clock (post) <= 90 s for both runners

Artifact-driven, not benchmark-running: producing the latest artifact is a
separate step (``uv run pyct-benchmark realworld --targets ... -o ...``).
The test is marked ``slow`` and excluded from the default suite — see the
slow-marker config in ``pyproject.toml`` for opt-in semantics.

Stale-baseline caveat: the default BASELINE points at the QRS 2026 run
(``benchmark/results/qrs_n10_20260418_193304``). Per memory note
``project_smt_perf_premise_obsolete.md``, that baseline was calibrated
against the pre-improvement engine — its urlsplit 90s bottleneck was
already collapsed by unrelated engine fixes that landed between April 18
and this feature's start. The pure_concolic ``>=`` assertion stays
meaningful (no regression), but the magnitude is not attributable to
this feature's encoding rewrites alone.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

import pytest

# Targets the spec called out as Mode-2 perf candidates for encoding rewrites.
# Mapped from benchmark test_name field. Memory: project_smt_perf_premise_obsolete.
_MODE_2_TARGETS: frozenset[str] = frozenset(
    {
        "Parse Content Range Header",
        "Parse Dict Header",
        "Parse List Header",
        "Validate URL",
        "URL Split",
    }
)

_PER_TARGET_TIMEOUT_S = 90.0
_LLM_COVERAGE_TOLERANCE_PP = 5.0

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_BASELINE = (
    _REPO_ROOT
    / "benchmark"
    / "results"
    / "qrs_n10_20260418_193304"
    / "realworld"
    / "trial_0"
    / "run_20260418_215802"
    / "results.json"
)
_DEFAULT_LATEST = (
    _REPO_ROOT
    / "benchmark"
    / "results"
    / "no_regression_latest"
    / "realworld"
    / "results.json"
)


def _resolve_path(env_var: str, default: Path) -> Path:
    override = os.environ.get(env_var)
    return Path(override) if override else default


def _load_results(path: Path) -> dict[str, dict]:
    """Return ``{test_name: result_entry}`` from a benchmark results.json."""
    payload = json.loads(path.read_text())
    return {entry["test_name"]: entry for entry in payload["results"]}


def _coverage_pct(entry: Mapping, runner: str) -> float:
    return float(entry["runners"][runner]["coverage"]["coverage_percent"])


def _wall_clock_s(entry: Mapping, runner: str) -> float:
    return float(entry["runners"][runner]["time_seconds"])


@pytest.mark.slow
def test_realworld_mode_2_targets_have_no_regression() -> None:
    baseline_path = _resolve_path("BASELINE_RESULTS", _DEFAULT_BASELINE)
    latest_path = _resolve_path("LATEST_RESULTS", _DEFAULT_LATEST)

    assert baseline_path.exists(), (
        f"baseline results not found at {baseline_path}. "
        f"Override via BASELINE_RESULTS env var."
    )
    assert latest_path.exists(), (
        f"latest results not found at {latest_path}. "
        f"Run the realworld benchmark for the Mode-2 targets and either "
        f"save to {_DEFAULT_LATEST} or set LATEST_RESULTS env var."
    )

    baseline = _load_results(baseline_path)
    latest = _load_results(latest_path)

    missing = _MODE_2_TARGETS - (baseline.keys() & latest.keys())
    assert not missing, (
        f"Mode-2 targets missing from one or both artifacts: {sorted(missing)}"
    )

    failures: list[str] = []
    for target in sorted(_MODE_2_TARGETS):
        b_pc = _coverage_pct(baseline[target], "pure_concolic")
        l_pc = _coverage_pct(latest[target], "pure_concolic")
        if l_pc < b_pc:
            failures.append(
                f"  [{target}] pure_concolic regressed: "
                f"baseline={b_pc:.2f}% -> latest={l_pc:.2f}%"
            )

        b_llm = _coverage_pct(baseline[target], "concolic_llm")
        l_llm = _coverage_pct(latest[target], "concolic_llm")
        if abs(l_llm - b_llm) > _LLM_COVERAGE_TOLERANCE_PP:
            failures.append(
                f"  [{target}] concolic_llm outside +/- "
                f"{_LLM_COVERAGE_TOLERANCE_PP}pp tolerance: "
                f"baseline={b_llm:.2f}% -> latest={l_llm:.2f}% "
                f"(delta={l_llm - b_llm:+.2f}pp)"
            )

        for runner in ("pure_concolic", "concolic_llm"):
            t = _wall_clock_s(latest[target], runner)
            if t > _PER_TARGET_TIMEOUT_S:
                failures.append(
                    f"  [{target}] {runner} exceeded {_PER_TARGET_TIMEOUT_S}s "
                    f"budget: {t:.2f}s"
                )

    assert not failures, "Mode-2 regression checks failed:\n" + "\n".join(failures)
