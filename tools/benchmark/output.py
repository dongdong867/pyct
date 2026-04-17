"""Output writers — JSON results, text summary, and rich console tables.

JSON schema matches legacy's run_20260327_030025/results.json for
cross-validation in M4. Console output uses box-drawing characters
for coverage/time comparison tables with winner indicators. The
``summary.txt`` writer produces a header + three stacked per-target
tables (coverage%, lines, time) + aggregate — enough context to
interpret a run without opening ``results.json``.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from tools.benchmark.models import BenchmarkConfig, RunnerResult

log = logging.getLogger("benchmark.output")


@dataclass(frozen=True)
class SummaryHeader:
    """Run-level metadata that tops the summary.txt file."""

    suite: str
    timestamp: str
    wall_clock_seconds: float
    target_count: int
    config: BenchmarkConfig


# ── Persistence ────────────────────────────────────────────────────


def save_results_json(
    all_results: list[dict[str, Any]],
    config: BenchmarkConfig,
    path: Path,
) -> None:
    """Write results.json matching legacy schema."""
    payload = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "config": config.to_dict(),
        "results": all_results,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")
    log.info("Results saved to %s", path)


def save_summary(
    all_results: list[dict[str, Any]],
    runner_names: list[str],
    path: Path,
    header: SummaryHeader | None = None,
) -> None:
    """Write an enriched summary.txt: header + 3 per-target tables + aggregate.

    When ``header`` is omitted, produces the legacy compact coverage
    table only — kept for ad-hoc callers that don't have run metadata.
    """
    if header is None:
        _write_legacy_summary(all_results, runner_names, path)
        return

    name_col = _resolve_name_column(all_results)

    lines: list[str] = []
    lines.extend(_format_header(header))
    lines.append("")
    lines.extend(_format_per_target_table(all_results, runner_names, _coverage_cell, name_col))
    lines.append("")
    if _has_engine_data(all_results):
        lines.extend(_format_engine_coverage_table(all_results, runner_names, name_col))
        lines.append("")
    lines.extend(_format_per_target_table(all_results, runner_names, _lines_cell, name_col))
    lines.append("")
    lines.extend(_format_per_target_table(all_results, runner_names, _time_cell, name_col))
    lines.append("")
    lines.extend(_format_aggregate_block(all_results, runner_names))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


def _write_legacy_summary(
    all_results: list[dict[str, Any]],
    runner_names: list[str],
    path: Path,
) -> None:
    lines: list[str] = []
    header_line = f"{'Target':<35s}" + "".join(f"  {rn:>12s}" for rn in runner_names)
    lines.append(header_line)
    lines.append("-" * len(header_line))
    for entry in all_results:
        name = entry["test_name"]
        parts = [f"{name:<35s}"]
        for rn in runner_names:
            runner_data = entry["runners"].get(rn)
            if runner_data is None:
                parts.append(f"{'N/A':>14s}")
            else:
                pct = runner_data.get("coverage", {}).get("coverage_percent", 0.0)
                parts.append(f"  {pct:>11.1f}%")
        lines.append("".join(parts))
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


# ── Summary formatters ────────────────────────────────────────────


def _format_header(h: SummaryHeader) -> list[str]:
    bar = "=" * 80
    return [
        bar,
        f" PyCT Benchmark — {h.suite} suite",
        bar,
        f" Timestamp:   {h.timestamp}",
        f" Wall-clock:  {_format_duration(h.wall_clock_seconds)}",
        f" Targets: {h.target_count}",
        "",
        " Config:",
        f"   timeout:         {h.config.timeout}s",
        f"   single_timeout:  {h.config.single_timeout}s",
        f"   max_iterations:  {h.config.max_iterations}",
        f"   num_attempts:    {h.config.num_attempts}",
        bar,
    ]


def _format_duration(seconds: float) -> str:
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _coverage_cell(runner_data: dict[str, Any]) -> str:
    pct = runner_data.get("coverage", {}).get("coverage_percent", 0.0)
    return f"{pct:>10.1f}%"


def _lines_cell(runner_data: dict[str, Any]) -> str:
    cov = runner_data.get("coverage", {})
    exec_ = cov.get("executed_lines", 0)
    total = cov.get("total_lines", 0)
    return f"{exec_:>5d}/{total:<5d}"


def _time_cell(runner_data: dict[str, Any]) -> str:
    return f"{runner_data.get('time_seconds', 0.0):>10.2f}"


_CELL_HEADERS = {
    _coverage_cell: ("COVERAGE (%)", "cov%"),
    _lines_cell: ("LINES (executed / total)", "exec/total"),
    _time_cell: ("TIME (seconds)", "seconds"),
}


_MAX_NAME_COL = 56
_DATA_COL = 14


def _resolve_name_column(all_results: list[dict[str, Any]]) -> int:
    """Compute a name column width that fits every test name up to a cap.

    ``"Target"`` is the minimum floor; any target longer than
    ``_MAX_NAME_COL`` gets truncated with a middle-ellipsis at render
    time, so the column width never exceeds the cap.
    """
    longest = max((len(entry["test_name"]) for entry in all_results), default=0)
    return min(max(longest, len("Target")), _MAX_NAME_COL)


def _truncate_middle(name: str, width: int) -> str:
    """Return ``name`` fit to ``width`` using a middle ``…`` if too long.

    Splitting in the middle preserves both the module prefix and the
    function suffix — the two halves most readers use to orient.
    """
    if len(name) <= width:
        return name
    keep = width - 1  # room for the ellipsis char
    left = keep - keep // 2
    right = keep // 2
    return f"{name[:left]}…{name[-right:]}"


def _format_per_target_table(
    all_results: list[dict[str, Any]],
    runner_names: list[str],
    cell_fn: Any,
    name_col: int,
) -> list[str]:
    section, _ = _CELL_HEADERS[cell_fn]
    header = f"{'Target':<{name_col}s}" + "".join(
        f" {rn:>{_DATA_COL}s}" for rn in runner_names
    )
    lines = [f"PER-TARGET {section}", "-" * len(header), header, "-" * len(header)]

    for entry in all_results:
        parts = [f"{_truncate_middle(entry['test_name'], name_col):<{name_col}s}"]
        for rn in runner_names:
            runner_data = entry["runners"].get(rn)
            if runner_data is None:
                parts.append(f" {'N/A':>{_DATA_COL}s}")
            else:
                parts.append(f" {cell_fn(runner_data):>{_DATA_COL}s}")
        lines.append("".join(parts))

    return lines


def _has_engine_data(all_results: list[dict[str, Any]]) -> bool:
    """True when any runner on any target exposed an engine_coverage_percent."""
    for entry in all_results:
        for runner_data in entry.get("runners", {}).values():
            if isinstance(runner_data, dict) and "engine_coverage_percent" in runner_data:
                return True
    return False


def _format_engine_coverage_table(
    all_results: list[dict[str, Any]],
    runner_names: list[str],
    name_col: int,
) -> list[str]:
    """Render the engine's in-loop wide-scope coverage per (target, runner).

    Only called when at least one runner has engine data. Cells without
    data read ``N/A`` — some runners (crosshair, llm_only) never route
    through the engine's tracker.
    """
    header = f"{'Target':<{name_col}s}" + "".join(
        f" {rn:>{_DATA_COL}s}" for rn in runner_names
    )
    title = "PER-TARGET ENGINE COVERAGE (%) — in-loop wide-scope"
    lines = [title, "-" * len(header), header, "-" * len(header)]

    for entry in all_results:
        parts = [f"{_truncate_middle(entry['test_name'], name_col):<{name_col}s}"]
        for rn in runner_names:
            runner_data = entry["runners"].get(rn)
            pct = (
                runner_data.get("engine_coverage_percent")
                if isinstance(runner_data, dict)
                else None
            )
            if pct is None:
                parts.append(f" {'N/A':>{_DATA_COL}s}")
            else:
                parts.append(f" {pct:>{_DATA_COL - 1}.1f}%")
        lines.append("".join(parts))

    return lines


def _format_aggregate_block(
    all_results: list[dict[str, Any]],
    runner_names: list[str],
) -> list[str]:
    stats = _compute_runner_stats(all_results)
    show_engine = _has_engine_data(all_results)
    bar = "=" * 80
    header = (
        f"{'Runner':<18s} {'Tests':<10s} {'Avg Cov':<10s} "
        + (f"{'Engine Cov':<12s} " if show_engine else "")
        + f"{'Avg Time':<12s} {'Total Time':<14s} {'Wins':<6s}"
    )
    lines = [bar, "AGGREGATE", bar, header, "-" * 80]

    for name in runner_names:
        s = stats.get(name)
        if s is None:
            continue
        ok = s["successful"]
        total = s["total"]
        avg_cov = s["total_coverage"] / ok if ok else 0.0
        avg_time = s["total_time"] / ok if ok else 0.0
        total_time = s["total_time"]
        row = (
            f"{name:<18s} "
            f"{f'{ok}/{total}':<10s} "
            f"{avg_cov:>6.1f}%   "
        )
        if show_engine:
            engine_n = s["engine_n"]
            row += (
                f"{s['total_engine_coverage'] / engine_n:>7.1f}%    "
                if engine_n
                else f"{'N/A':>11s} "
            )
        row += (
            f"{avg_time:>8.2f}s   "
            f"{_format_duration(total_time):<14s} "
            f"{s['wins']:<6d}"
        )
        lines.append(row)
    lines.append(bar)
    return lines


# ── Per-target console output ──────────────────────────────────────


def format_test_header(
    target_name: str,
    category: str,
    description: str,
    function: str = "",
) -> str:
    """Format the header for a single test run."""
    lines = [
        f"\n{'=' * 80}",
        f"TEST: {target_name}",
        f"Category: {category}",
        f"Description: {description}",
    ]
    if function:
        lines.append(f"Function: {function}()")
    lines.append("=" * 80)
    return "\n".join(lines)


def format_runner_result(runner_name: str, result: RunnerResult) -> str:
    """Format one runner's result with status indicators and token stats."""
    lines = [f"\n[{runner_name.upper()}]"]
    if result.success:
        cov = result.coverage
        lines.append(
            f"  \u2713 Coverage: {cov.coverage_percent:.1f}% "
            f"({cov.executed_lines}/{cov.total_lines} lines)"
        )
        lines.append(f"  \u2713 Time: {result.time_seconds:.2f}s")
        if result.attempts:
            lines.append(f"  \u2713 Attempts: {len(result.attempts)}")
        if result.iterations is not None:
            lines.append(f"  \u2713 Iterations: {result.iterations}")
        if result.test_cases_generated is not None:
            lines.append(f"  \u2713 Test cases: {result.test_cases_generated}")
        if result.token_usage is not None:
            tu = result.token_usage
            total = tu.input_tokens + tu.output_tokens
            lines.append(
                f"  \u2713 Tokens: {total:,} (in: {tu.input_tokens:,}, out: {tu.output_tokens:,})"
            )
    else:
        lines.append(f"  \u2717 Failed: {result.error or 'Unknown error'}")
    return "\n".join(lines)


def format_comparison_table(runner_results: dict[str, RunnerResult]) -> str:
    """Format coverage + time comparison tables with box-drawing and winners."""
    successful = {n: r for n, r in runner_results.items() if r.success}
    if not successful:
        return "  No successful runs to compare"

    max_cov = max(r.coverage.coverage_percent for r in successful.values())
    min_time = min(r.time_seconds for r in successful.values())

    lines = _build_coverage_table(successful, max_cov)
    lines.append("")
    lines.extend(_build_time_table(successful, min_time))

    winner = max(successful, key=lambda n: successful[n].coverage.coverage_percent)
    fastest = min(successful, key=lambda n: successful[n].time_seconds)
    lines.extend(
        [
            "",
            "  Summary:",
            f"    \u2022 Best Coverage: {winner.upper()} ({max_cov:.1f}%)",
            f"    \u2022 Fastest: {fastest.upper()} ({min_time:.2f}s)",
        ]
    )
    return "\n".join(lines)


# ── Aggregate summary ──────────────────────────────────────────────


def format_summary_table(
    all_results: list[dict[str, Any]],
    runner_names: list[str],
) -> str:
    """Format aggregate statistics across all tests with win counts."""
    stats = _compute_runner_stats(all_results)

    lines = [
        f"\n{'=' * 80}",
        "SUMMARY",
        f"{'=' * 80}\n",
        f"{'Runner':<20s} {'Tests':<10s} {'Avg Cov':<12s} {'Avg Time':<12s} {'Wins':<10s}",
        "-" * 70,
    ]

    for name in runner_names:
        s = stats.get(name)
        if s is None:
            continue
        ok = s["successful"]
        total = s["total"]
        avg_cov = s["total_coverage"] / ok if ok > 0 else 0
        avg_time = s["total_time"] / ok if ok > 0 else 0
        wins = s["wins"]
        ratio = f"{ok}/{total}"
        lines.append(f"{name:<20s} {ratio:<8s} {avg_cov:>7.1f}%     {avg_time:>7.2f}s      {wins}")

    lines.append("=" * 80)
    return "\n".join(lines)


# ── Box-drawing tables ─────────────────────────────────────────────

_W1 = 19  # first column width
_W2 = 12  # data column width


def _build_coverage_table(
    results: dict[str, RunnerResult],
    max_cov: float,
) -> list[str]:
    """Coverage comparison with box-drawing borders."""
    lines = [
        "\u250c"
        + "\u2500" * (_W1 + 2)
        + "\u252c"
        + "\u2500" * (_W2 + 2)
        + "\u252c"
        + "\u2500" * 24
        + "\u2510",
        "\u2502" + " COVERAGE COMPARISON".center(_W1 + _W2 + 28) + "\u2502",
        "\u251c"
        + "\u2500" * (_W1 + 2)
        + "\u253c"
        + "\u2500" * (_W2 + 2)
        + "\u253c"
        + "\u2500" * 24
        + "\u2524",
        "\u2502"
        + " Runner".ljust(_W1 + 2)
        + "\u2502"
        + " Coverage".ljust(_W2 + 2)
        + "\u2502"
        + " Lines (Exec/Total)".ljust(24)
        + "\u2502",
        "\u251c"
        + "\u2500" * (_W1 + 2)
        + "\u253c"
        + "\u2500" * (_W2 + 2)
        + "\u253c"
        + "\u2500" * 24
        + "\u2524",
    ]
    for name, result in results.items():
        cov = result.coverage
        name_col = f" {name.upper()[:_W1]:<{_W1}s}"
        star = " \u2605" if cov.coverage_percent == max_cov else ""
        cov_col = f" {cov.coverage_percent:5.1f}%{star}".ljust(_W2 + 2)
        lines_col = f" {cov.executed_lines}/{cov.total_lines}".ljust(24)
        lines.append(f"\u2502{name_col} \u2502{cov_col}\u2502{lines_col}\u2502")
    lines.append(
        "\u2514"
        + "\u2500" * (_W1 + 2)
        + "\u2534"
        + "\u2500" * (_W2 + 2)
        + "\u2534"
        + "\u2500" * 24
        + "\u2518"
    )
    return lines


def _build_time_table(
    results: dict[str, RunnerResult],
    min_time: float,
) -> list[str]:
    """Time comparison with box-drawing borders."""
    lines = [
        "\u250c"
        + "\u2500" * (_W1 + 2)
        + "\u252c"
        + "\u2500" * (_W2 + 2)
        + "\u252c"
        + "\u2500" * 24
        + "\u2510",
        "\u2502" + " TIME COMPARISON".center(_W1 + _W2 + 28) + "\u2502",
        "\u251c"
        + "\u2500" * (_W1 + 2)
        + "\u253c"
        + "\u2500" * (_W2 + 2)
        + "\u253c"
        + "\u2500" * 24
        + "\u2524",
        "\u2502"
        + " Runner".ljust(_W1 + 2)
        + "\u2502"
        + " Time (s)".ljust(_W2 + 2)
        + "\u2502"
        + " Additional Info".ljust(24)
        + "\u2502",
        "\u251c"
        + "\u2500" * (_W1 + 2)
        + "\u253c"
        + "\u2500" * (_W2 + 2)
        + "\u253c"
        + "\u2500" * 24
        + "\u2524",
    ]
    for name, result in results.items():
        name_col = f" {name.upper()[:_W1]:<{_W1}s}"
        star = " \u2605" if result.time_seconds == min_time else ""
        time_col = f" {result.time_seconds:6.2f}{star}".ljust(_W2 + 2)
        info_parts = []
        if result.iterations is not None:
            info_parts.append(f"iter:{result.iterations}")
        if result.test_cases_generated is not None:
            info_parts.append(f"tests:{result.test_cases_generated}")
        if result.token_usage is not None:
            total_tok = result.token_usage.input_tokens + result.token_usage.output_tokens
            info_parts.append(f"tok:{total_tok:,}")
        info_col = f" {', '.join(info_parts) or '-'}"[:24].ljust(24)
        lines.append(f"\u2502{name_col} \u2502{time_col}\u2502{info_col}\u2502")
    lines.append(
        "\u2514"
        + "\u2500" * (_W1 + 2)
        + "\u2534"
        + "\u2500" * (_W2 + 2)
        + "\u2534"
        + "\u2500" * 24
        + "\u2518"
    )
    return lines


# ── Stats aggregation ──────────────────────────────────────────────


def _compute_runner_stats(
    all_results: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Aggregate per-runner statistics across all test results.

    ``total_engine_coverage`` and ``engine_n`` are the dual-reporting
    counterparts to ``total_coverage`` and ``successful``: they sum
    engine-in-loop percentages only over targets where the runner
    actually exposed an ``engine_coverage_percent``. This avoids
    polluting the average with zeros from runners that never route
    through the engine (``crosshair``, ``llm_only``).
    """
    stats: dict[str, dict[str, Any]] = {}

    for entry in all_results:
        runners = entry.get("runners", {})
        for name, result_data in runners.items():
            if name not in stats:
                stats[name] = {
                    "total": 0,
                    "successful": 0,
                    "total_coverage": 0.0,
                    "total_time": 0.0,
                    "wins": 0,
                    "total_engine_coverage": 0.0,
                    "engine_n": 0,
                }
            s = stats[name]
            s["total"] += 1
            if isinstance(result_data, dict) and result_data.get("success"):
                s["successful"] += 1
                s["total_coverage"] += result_data["coverage"]["coverage_percent"]
                s["total_time"] += result_data["time_seconds"]
                engine_pct = result_data.get("engine_coverage_percent")
                if engine_pct is not None:
                    s["total_engine_coverage"] += engine_pct
                    s["engine_n"] += 1

    _count_wins(all_results, stats)
    return stats


def _count_wins(
    all_results: list[dict[str, Any]],
    stats: dict[str, dict[str, Any]],
) -> None:
    """Determine the coverage winner per test and update win counts."""
    for entry in all_results:
        runners = entry.get("runners", {})
        best_name = None
        best_cov = -1.0
        for name, result_data in runners.items():
            if isinstance(result_data, dict) and result_data.get("success"):
                pct = result_data["coverage"]["coverage_percent"]
                if pct > best_cov:
                    best_cov = pct
                    best_name = name
        if best_name and best_name in stats:
            stats[best_name]["wins"] += 1
