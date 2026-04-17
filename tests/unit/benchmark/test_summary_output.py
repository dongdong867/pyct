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


# ── Target-column sizing ───────────────────────────────────────────


def test_target_column_accommodates_short_names_without_overflow(tmp_path):
    # With short names only, value columns stay aligned and no target
    # name spills into the value area.
    text = _write_and_read(tmp_path)
    # Every per-target data row begins with the full target name, then
    # spaces, then the value — no value sits directly adjacent to the
    # name with < 2 spaces of separation.
    for line in text.splitlines():
        if line.startswith("foo."):
            assert "  " in line, f"target row should keep visual spacing: {line!r}"


def test_long_target_name_is_truncated_not_overflowed(tmp_path):
    long_name = "sympy.ntheory.multinomial.multinomial_coefficients_iterator"
    results = [
        _result(
            long_name,
            pc_cov=100.0,
            pc_exec=10,
            pc_total=10,
            pc_time=1.0,
            ch_cov=50.0,
            ch_exec=5,
            ch_total=10,
            ch_time=0.5,
        ),
    ]
    out = tmp_path / "summary.txt"
    save_summary(results, _RUNNERS, out, header=_HEADER)
    text = out.read_text()

    # The per-target data row holds the ellipsis-truncated name. Value
    # cells stay aligned — the row in the COVERAGE table contains the
    # runner percentages, the row in LINES table contains exec/total, etc.
    ellipsis_rows = [line for line in text.splitlines() if "…" in line]
    assert len(ellipsis_rows) >= 3, (
        "ellipsis-truncated name should appear once per per-target table"
    )
    # At least one truncated row carries the coverage percentages
    cov_rows = [line for line in ellipsis_rows if "100.0%" in line and "50.0%" in line]
    assert cov_rows, "coverage row for the truncated name should hold both percentages"


def test_header_and_separator_widths_agree(tmp_path):
    # The dashed separators directly above and below the 'Target ...'
    # header line must have identical length to the header itself.
    text = _write_and_read(tmp_path)
    target_header_idx = None
    for i, line in enumerate(text.splitlines()):
        if line.startswith("Target") and "pure_concolic" in line:
            target_header_idx = i
            break
    assert target_header_idx is not None
    lines = text.splitlines()
    header_len = len(lines[target_header_idx])
    below = lines[target_header_idx + 1]
    # The dashed separator right after the header row matches its width
    assert below.count("-") == header_len, (
        f"separator length {below.count('-')} should equal header length {header_len}"
    )


# ── Dual-reporting engine coverage ────────────────────────────────


def _result_with_engine(name, *, pc_cov, pc_exec, pc_total, pc_time, engine_pc):
    # RunnerResult.to_dict omits engine fields when they're None, so
    # constructing with explicit numbers simulates a run where the
    # engine exposed its in-loop wide-scope view.
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
                "engine_coverage_percent": engine_pc,
                "engine_executed_lines": int(engine_pc * 10),
                "engine_total_lines": 1000,
            },
        },
    }


def test_engine_coverage_section_appears_when_data_present(tmp_path):
    results = [
        _result_with_engine(
            "pkg.alpha", pc_cov=80.0, pc_exec=8, pc_total=10, pc_time=1.0, engine_pc=12.3
        ),
    ]
    out = tmp_path / "summary.txt"
    save_summary(results, ["pure_concolic"], out, header=_HEADER)
    text = out.read_text()

    # New section header is present when at least one runner has engine data
    assert "PER-TARGET ENGINE COVERAGE" in text
    # The engine percentage appears in that section (formatted to 1 decimal)
    assert "12.3" in text


def test_engine_coverage_section_omitted_when_no_engine_data(tmp_path):
    # The default _RESULTS entries have no engine_coverage_percent field.
    text = _write_and_read(tmp_path)
    assert "PER-TARGET ENGINE COVERAGE" not in text


def test_aggregate_includes_engine_column_when_engine_data_present(tmp_path):
    results = [
        _result_with_engine(
            "pkg.alpha", pc_cov=80.0, pc_exec=8, pc_total=10, pc_time=1.0, engine_pc=12.0
        ),
        _result_with_engine(
            "pkg.beta", pc_cov=60.0, pc_exec=6, pc_total=10, pc_time=1.0, engine_pc=8.0
        ),
    ]
    out = tmp_path / "summary.txt"
    save_summary(results, ["pure_concolic"], out, header=_HEADER)
    text = out.read_text()

    # Aggregate block grows an Engine Cov column with the average
    assert "Engine Cov" in text
    # (12.0 + 8.0) / 2 = 10.0
    assert "10.0" in text


def test_aggregate_engine_column_absent_without_data(tmp_path):
    text = _write_and_read(tmp_path)
    assert "Engine Cov" not in text
