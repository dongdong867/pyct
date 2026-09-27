"""The rows a sweep prints, its summary line, and the lines it tells people on stderr.

stdout carries one JSON line per row, then the summary line; stderr is for
people (output-stdout-data-stderr-log). Every row has the same six keys,
null when empty. A tool tells the summary from a row by ``swept``.
"""

import json
import platform
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

# the limits each entry's pyct run gets with no flags, as the summary reports them
LIMITS: Mapping[str, object] = {
    "budget": 30.0,
    "plateau": 5,
    "solver_timeout": 10.0,
    "total_budget": None,
}


class Status(StrEnum):
    """What became of a row's entry, or of a module that did not import."""

    RAN = "ran"
    FAILED = "failed"
    SKIPPED = "skipped"
    LISTED = "listed"


@dataclass(frozen=True)
class Row:
    """One entry, or one module that did not import, whose ``name`` is None."""

    module: str
    name: str | None
    status: Status
    seed: Mapping[str, object] | None = None
    reason: str | None = None

    @property
    def order(self) -> tuple[str, str]:
        """Module name, then entry name, in Python's string order; a module's own row first."""
        return (self.module, self.name or "")


def row_line(row: Row) -> str:
    """One row as its JSON line. ``run`` is null: no entry has run."""
    return json.dumps(
        {
            "module": row.module,
            "name": row.name,
            "status": row.status.value,
            "seed": row.seed,
            "reason": row.reason,
            "run": None,
        }
    )


def summary_line(package: str, rows: Sequence[Row]) -> str:
    """The line that closes stdout for a sweep that listed its entries and ran none."""
    counts = {status.value: _count(rows, status) for status in Status}
    environment = {
        "python": platform.python_version(),
        "cvc5": None,
        "platform": platform.platform(),
    }
    payload = {"swept": package, "stopped": "listed", **counts}
    payload |= {"covered": {}, "total": {}, "limits": dict(LIMITS), "environment": environment}
    return json.dumps(payload)


def told(row: Row) -> str | None:
    """The stderr line after a row, or None for a listed one, which says nothing more."""
    if row.status is Status.SKIPPED:
        return f"skipped {row.module}::{row.name}: {row.reason}"
    if row.status is Status.FAILED:
        return f"failed {row.module}: {row.reason}"
    return None


def closing(package: str, rows: Sequence[Row]) -> str:
    """The stderr lines that end a listing: what was found, the counts, and why it stopped."""
    lines = [] if any(row.name is not None for row in rows) else [f"found no entries in {package}"]
    listed, skipped, failed = (
        _count(rows, s) for s in (Status.LISTED, Status.SKIPPED, Status.FAILED)
    )
    lines.append(f"listed {len(rows)} entries: {listed} listed, {skipped} skipped, {failed} failed")
    lines.append("stopped: listed")
    return "".join(f"{line}\n" for line in lines)


def _count(rows: Sequence[Row], status: Status) -> int:
    return sum(1 for row in rows if row.status is status)
