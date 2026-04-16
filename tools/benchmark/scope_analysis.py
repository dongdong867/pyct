"""Entered-scope coverage analysis for library/realworld targets.

For external-package targets, function-level coverage is misleading
(entry functions are thin wrappers). Entered-scope coverage narrows
the denominator to functions that were actually called: if at least
one line in a function executed, all its executable lines count toward
the total. Unreached functions are excluded entirely.

Port of legacy's benchmark/coverage/scope_analysis.py.
"""

from __future__ import annotations

import ast
import logging

from coverage import Coverage

from tools.benchmark.models import CoverageResult

log = logging.getLogger("benchmark.scope")


def measure_entered_scope_coverage(
    cov: Coverage,
    source_path: str,
) -> CoverageResult:
    """Compute entered-scope coverage from a coverage.py session.

    Args:
        cov: A stopped coverage.py session with measurement data.
        source_path: Root directory of the package source. Only files
            under this path are analyzed.

    Returns:
        CoverageResult where total_lines = executable lines in entered
        functions, executed_lines = covered lines in those functions.
    """
    data = cov.get_data()

    total_entered = 0
    total_covered = 0
    all_exec_lines: list[int] = []
    all_miss_lines: list[int] = []

    for filepath in data.measured_files():
        if not filepath.startswith(source_path):
            continue

        hit = set(data.lines(filepath) or [])
        if not hit:
            continue

        try:
            _, stmts, _, _ = cov.analysis(filepath)
        except Exception:
            continue
        executable = set(stmts)

        func_ranges = _collect_function_ranges(filepath)
        entered_exec, entered_hit = _compute_entered_lines(
            func_ranges, executable, hit,
        )

        total_entered += len(entered_exec)
        total_covered += len(entered_hit)
        all_exec_lines.extend(sorted(entered_hit))
        all_miss_lines.extend(sorted(entered_exec - entered_hit))

    pct = (total_covered / total_entered * 100) if total_entered > 0 else 0.0

    return CoverageResult(
        coverage_percent=pct,
        executed_lines=total_covered,
        total_lines=total_entered,
        executed_line_numbers=sorted(all_exec_lines),
        missing_line_numbers=sorted(all_miss_lines),
    )


def _collect_function_ranges(filepath: str) -> list[tuple[int, int]]:
    """Parse a file and return (start, end) for every function/method."""
    try:
        with open(filepath) as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError):
        return []

    ranges: list[tuple[int, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(node, "end_lineno", None) or node.lineno
            ranges.append((node.lineno, end))
    return ranges


def _compute_entered_lines(
    func_ranges: list[tuple[int, int]],
    executable: set[int],
    hit: set[int],
) -> tuple[set[int], set[int]]:
    """Return (entered_executable, entered_covered) across all entered scopes.

    A scope is "entered" when at least one of its executable lines was
    hit. Applies def-line inclusion within each entered function.
    Module-level code (outside any function) is treated as one scope.
    """
    entered_exec: set[int] = set()
    entered_hit: set[int] = set()

    for start, end in func_ranges:
        scope_exec = executable & set(range(start, end + 1))
        scope_hit = scope_exec & hit
        if scope_hit:
            entered_exec |= scope_exec
            entered_hit |= scope_hit
            # Def-line inclusion: lines before first hit are covered
            first = min(scope_hit)
            for s in scope_exec:
                if s < first:
                    entered_hit.add(s)

    # Module-level lines (outside any function)
    all_func_lines: set[int] = set()
    for start, end in func_ranges:
        all_func_lines |= executable & set(range(start, end + 1))
    module_level = executable - all_func_lines
    module_hit = module_level & hit
    if module_hit:
        entered_exec |= module_level
        entered_hit |= module_hit

    return entered_exec, entered_hit
