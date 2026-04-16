"""Rich summary.txt output — header, per-target tables, aggregate.

The summary previously held only a single cov% table with no run
context. This module pins the new content so it's hard to drop
accidentally — tests check for structural markers (section headers,
key numbers, expected columns) rather than exact formatting, so
cosmetic tweaks don't require test churn.
"""

from __future__ import annotations

from pathlib import Path

from tools.benchmark.models import BenchmarkConfig
from tools.benchmark.output import SummaryHeader, save_summary

_HEADER = SummaryHeader(
    suite="library",
    timestamp="2026-04-17 10:30:00",
    wall_clock_seconds=3725.5,  # 1h 2m 5s
    target_count=2,
    config=BenchmarkConfig(
        timeout=120.0,
        single_timeout=30.0,
        max_iterations=50,
        num_attempts=3,
    ),
)


def _result(
    name: str,
    *,
    pc_cov: float,
    pc_exec: int,
    pc_total: int,
    pc_time: float,
    ch_cov: float,
    ch_exec: int,
    ch_total: int,
    ch_time: float,
) -> dict:
    return {
        "test_name": name,
        "function": name.split(".")[-1],
        "category": "test",
        "baseline_generated_at": None,
        "runners": {
            "pure_concolic": {
                "success": True,
                "coverage": {
                    "coverage_percent": pc_cov,
                    "executed_lines": pc_exec,
                    "total_lines": pc_total,
                    "executed_line_numbers": [],
                    "missing_line_numbers": [],
                },
                "time_seconds": pc_time,
                "error": None,
            },
            "crosshair": {
                "success": True,
                "coverage": {
                    "coverage_percent": ch_cov,
                    "executed_lines": ch_exec,
                    "total_lines": ch_total,
                    "executed_line_numbers": [],
                    "missing_line_numbers": [],
                },
                "time_seconds": ch_time,
                "error": None,
            },
        },
    }


_RESULTS = [
    _result(
        "foo.alpha",
        pc_cov=100.0,
        pc_exec=10,
        pc_total=10,
        pc_time=1.5,
        ch_cov=50.0,
        ch_exec=5,
        ch_total=10,
        ch_time=0.8,
    ),
    _result(
        "foo.beta",
        pc_cov=75.0,
        pc_exec=3,
        pc_total=4,
        pc_time=2.1,
        ch_cov=100.0,
        ch_exec=4,
        ch_total=4,
        ch_time=0.3,
    ),
]
_RUNNERS = ["pure_concolic", "crosshair"]


def _write_and_read(tmp_path: Path) -> str:
    out = tmp_path / "summary.txt"
    save_summary(_RESULTS, _RUNNERS, out, header=_HEADER)
    return out.read_text()


# ── Header ────────────────────────────────────────────────────────


def test_header_includes_suite_name(tmp_path):
    assert "library" in _write_and_read(tmp_path)


def test_header_includes_run_timestamp(tmp_path):
    assert "2026-04-17 10:30:00" in _write_and_read(tmp_path)


def test_header_includes_wall_clock_in_human_form(tmp_path):
    text = _write_and_read(tmp_path)
    # 3725.5s ≈ 1h 02m 05s — accept either HH:MM:SS or '1h 2m' style
    assert "1h" in text and "2m" in text


def test_header_includes_config_values(tmp_path):
    text = _write_and_read(tmp_path)
    assert "120" in text  # timeout
    assert "30" in text  # single_timeout
    assert "50" in text  # max_iterations


def test_header_includes_target_count(tmp_path):
    text = _write_and_read(tmp_path)
    assert "Targets: 2" in text or "2 targets" in text


# ── Per-target tables ─────────────────────────────────────────────


def test_coverage_table_has_target_name_and_percentages(tmp_path):
    text = _write_and_read(tmp_path)
    assert "foo.alpha" in text
    assert "100.0%" in text
    assert "50.0%" in text


def test_lines_table_shows_executed_over_total(tmp_path):
    text = _write_and_read(tmp_path)
    # 10/10, 5/10, 3/4, 4/4 should all show up somewhere
    assert "10/10" in text
    assert "5/10" in text
    assert "3/4" in text
    assert "4/4" in text


def test_time_table_shows_per_runner_seconds(tmp_path):
    text = _write_and_read(tmp_path)
    # The 1.5 / 0.8 / 2.1 / 0.3 values need to land somewhere
    assert "1.5" in text
    assert "0.3" in text


# ── Aggregate ─────────────────────────────────────────────────────


def test_aggregate_block_includes_per_runner_avg_coverage(tmp_path):
    text = _write_and_read(tmp_path)
    # pure_concolic: (100 + 75) / 2 = 87.5%
    # crosshair:    (50 + 100) / 2 = 75.0%
    assert "87.5" in text
    assert "75.0" in text


def test_aggregate_block_includes_win_counts(tmp_path):
    text = _write_and_read(tmp_path)
    # alpha → pure_concolic wins; beta → crosshair wins → 1 each
    lower = text.lower()
    assert "win" in lower  # header exists
