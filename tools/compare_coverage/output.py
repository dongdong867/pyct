"""What the checker prints: JSON on stdout for tools, a table on stderr for a person.

stdout carries one JSON line per row as each finishes, then one summary line, which has
``statuses`` and no ``target``. stderr carries one table line per row, then the totals.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from tools.compare_coverage.rows import Row, SideView, Status

MARKS = ("accepted", "changed")


@dataclass(frozen=True)
class Facts:
    """Where the run ran: each checkout's commit, each side's Python, cvc5, the platform."""

    commits: Mapping[str, str | None]
    python: Mapping[str, str | None]
    cvc5: str | None
    platform: str


def row_line(row: Row) -> str:
    """One row as one JSON line."""
    return json.dumps(
        {
            "set": row.set,
            "target": row.target,
            "seed": row.seed,
            "file": row.file,
            "own_lines": list(row.own_lines),
            "status": row.status.value,
            "only_legacy": list(row.only_legacy),
            "only_v2": list(row.only_v2),
            "v2": _side(row.v2),
            "legacy": _side(row.legacy),
            "record": row.record,
            "change": row.change,
            "left_out": row.left_out,
        }
    )


def _side(view: SideView | None) -> dict[str, object] | None:
    if view is None:
        return None
    return {
        "file": view.file,
        "covered": list(view.covered),
        "stopped": view.stopped,
        "inputs": view.inputs,
        "failure": view.failure,
    }


def counts(rows: Sequence[Row]) -> dict[str, int]:
    """How many rows have each status, then how many are accepted and changed."""
    statuses = {status.value: sum(row.status is status for row in rows) for status in Status}
    return {**statuses, **{mark: sum(row.record == mark for row in rows) for mark in MARKS}}


def summary_line(
    rows: Sequence[Row], limits: Mapping[str, Mapping[str, float]], facts: Facts
) -> str:
    """The line that closes stdout: the counts, each side's limits, and where the run ran."""
    return json.dumps(
        {
            "statuses": counts(rows),
            "limits": limits,
            "commits": facts.commits,
            "environment": {
                "python": facts.python,
                "cvc5": facts.cvc5,
                "platform": facts.platform,
            },
        }
    )


def table_line(row: Row) -> str:
    """One row for a person: set, target, each side's lines, the status and what stands out."""
    parts = [row.set, row.target or row.file]
    if row.v2 is not None and row.legacy is not None:
        parts += [_side_text("v2", row.v2, row), _side_text("legacy", row.legacy, row)]
    parts.append(row.status.value if row.record is None else f"{row.status.value}, {row.record}")
    details = _details(row)
    return "  ".join(parts + ["; ".join(details)] if details else parts)


def _side_text(name: str, view: SideView, row: Row) -> str:
    stopped = view.stopped or "no stop"
    inputs = "?" if view.inputs is None else view.inputs
    covered = f"covered {len(view.covered)} of {len(row.own_lines)}"
    return f"{name} {covered} ({stopped}, {inputs} inputs)"


def _details(row: Row) -> list[str]:
    details = [] if row.left_out is None else [row.left_out]
    if row.change is not None:
        details.append(f"changed: {row.change}")
    for name, view in (("v2", row.v2), ("legacy", row.legacy)):
        if view is not None and view.failure is not None:
            details.append(f"{name}: {view.failure}")
    if row.only_legacy:
        details.append(f"only legacy: {', '.join(map(str, row.only_legacy))}")
    if row.only_v2:
        details.append(f"only v2: {', '.join(map(str, row.only_v2))}")
    return details


def totals_line(rows: Sequence[Row]) -> str:
    """The table's last line: every count the summary line carries."""
    return "totals: " + ", ".join(f"{name} {count}" for name, count in counts(rows).items())
