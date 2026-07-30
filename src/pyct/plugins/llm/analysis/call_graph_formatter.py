"""Format call graph analysis as text for LLM prompts.

Converts a :class:`CallGraphAnalysis` into a compact, actionable
representation that tells the LLM about branch conditions, boundary
values, and function sources across the entire call graph.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyct.plugins.llm.analysis.call_graph import AnalyzedFunction, CallGraphAnalysis


def format_call_graph_for_llm(analysis: CallGraphAnalysis) -> str:
    """Format *analysis* as text suitable for an LLM seed-generation prompt."""
    parts: list[str] = []
    parts.append("## Call Graph Analysis\n")

    _append_target_summary(parts, analysis)
    _append_callee_sections(parts, analysis)
    _append_aggregated_constraints(parts, analysis)
    _append_boundary_values(parts, analysis)

    return "\n".join(parts)


# ------------------------------------------------------------------
# Section builders
# ------------------------------------------------------------------


def _append_target_summary(parts: list[str], analysis: CallGraphAnalysis) -> None:
    target = analysis.target
    callee_names = ", ".join(target.callees) if target.callees else "(none)"
    parts.append(f"### Target: {target.name}{target.signature}")
    parts.append(f"Calls: {callee_names}\n")


def _append_callee_sections(parts: list[str], analysis: CallGraphAnalysis) -> None:
    if not analysis.reachable_functions:
        return

    by_depth = sorted(
        analysis.reachable_functions.values(), key=lambda f: (f.depth, f.name)
    )
    for func in by_depth:
        _append_single_function(parts, func)


def _append_single_function(parts: list[str], func: AnalyzedFunction) -> None:
    parts.append(
        f"### Called Function: {func.name}{func.signature}  [depth {func.depth}]"
    )
    parts.append(f"```python\n{func.source.rstrip()}\n```")

    if func.branch_conditions:
        parts.append("Branch conditions:")
        for cond in func.branch_conditions:
            parts.append(f"  - {cond}")

    if func.literals:
        literal_str = ", ".join(repr(v) for v in func.literals)
        parts.append(f"Boundary values: {literal_str}")

    parts.append("")  # blank line between functions


def _append_aggregated_constraints(
    parts: list[str],
    analysis: CallGraphAnalysis,
) -> None:
    """Collect branch conditions across ALL functions (target + callees)."""
    entries: list[str] = []
    _collect_conditions(entries, analysis.target)
    for func in sorted(analysis.reachable_functions.values(), key=lambda f: f.name):
        _collect_conditions(entries, func)

    if not entries:
        return
    parts.append("### Aggregated Constraints")
    parts.append(
        "All branch conditions across the call graph that inputs must satisfy:"
    )
    for i, entry in enumerate(entries, 1):
        parts.append(f"  {i}. {entry}")
    parts.append("")


def _collect_conditions(entries: list[str], func: AnalyzedFunction) -> None:
    for cond in func.branch_conditions:
        entries.append(f"{cond}  [in {func.name}]")


def _append_boundary_values(
    parts: list[str],
    analysis: CallGraphAnalysis,
) -> None:
    """Merge boundary values from all analyzed functions."""
    numeric: set[int | float] = set()
    strings: set[str] = set()

    for func in [analysis.target, *analysis.reachable_functions.values()]:
        for lit in func.literals:
            if isinstance(lit, (int, float)):
                numeric.add(lit)
            elif isinstance(lit, str):
                strings.add(lit)

    if not numeric and not strings:
        return
    parts.append("### Boundary Values")
    if numeric:
        parts.append(f"Numeric: {', '.join(str(v) for v in sorted(numeric))}")
    if strings:
        parts.append(f"Strings: {', '.join(repr(v) for v in sorted(strings))}")
    parts.append("")
