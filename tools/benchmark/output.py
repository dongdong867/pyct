"""Output writers — JSON results and text summary.

JSON schema matches legacy's run_20260327_030025/results.json for
cross-validation in M4. Summary is a compact text table.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from tools.benchmark.models import BenchmarkConfig, RunnerResult

log = logging.getLogger("benchmark.output")


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
) -> None:
    """Write a compact summary.txt table."""
    lines: list[str] = []
    lines.append(_summary_header(runner_names))
    lines.append("-" * len(lines[0]))

    for entry in all_results:
        name = entry["test_name"]
        parts = [f"{name:<35s}"]
        for rn in runner_names:
            runner_data = entry["runners"].get(rn)
            if runner_data is None:
                parts.append(f"{'N/A':>10s}")
            else:
                pct = runner_data.get("coverage", {}).get("coverage_percent", 0.0)
                parts.append(f"{pct:>9.1f}%")
        lines.append("  ".join(parts))

    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def format_test_header(target_name: str, category: str, description: str) -> str:
    """Format a test header for console output."""
    return f"\n{'='*60}\n{target_name} [{category}]\n  {description}\n{'='*60}"


def format_runner_line(runner_name: str, result: RunnerResult) -> str:
    """Format one runner's result for console output."""
    pct = result.coverage.coverage_percent
    t = result.time_seconds
    status = "OK" if result.success else "FAIL"
    iters = str(result.iterations) if result.iterations is not None else "-"
    return f"  {runner_name:<18s} {pct:>6.1f}%  {t:>7.1f}s  {iters:>4s} iters  [{status}]"


def format_comparison_table(runner_results: dict[str, RunnerResult]) -> str:
    """Format a comparison table of all runners for one target."""
    lines = []
    for name, result in runner_results.items():
        lines.append(format_runner_line(name, result))
    return "\n".join(lines)


def format_summary_table(
    all_results: list[dict[str, Any]],
    runner_names: list[str],
) -> str:
    """Format the final summary table for console output."""
    lines: list[str] = ["\n" + "=" * 70, "SUMMARY", "=" * 70]
    header = f"{'Target':<35s}" + "".join(f"  {rn:>12s}" for rn in runner_names)
    lines.append(header)
    lines.append("-" * len(header))

    for entry in all_results:
        name = entry["test_name"]
        parts = [f"{name:<35s}"]
        for rn in runner_names:
            runner_data = entry["runners"].get(rn, {})
            pct = runner_data.get("coverage", {}).get("coverage_percent", 0.0)
            parts.append(f"  {pct:>11.1f}%")
        lines.append("".join(parts))

    lines.append("=" * 70)
    return "\n".join(lines)


def _summary_header(runner_names: list[str]) -> str:
    """Build the header line for the summary table."""
    parts = [f"{'Target':<35s}"]
    for rn in runner_names:
        parts.append(f"{rn:>10s}")
    return "  ".join(parts)
