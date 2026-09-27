"""The rows a sweep prints, and the lines it tells people about each on stderr.

stdout carries one JSON line per row, then the summary line; stderr is for
people (output-stdout-data-stderr-log). Every row has the same six keys,
null when empty.
"""

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import cast


class Status(StrEnum):
    """What became of a row's entry, or of a module that did not import or could not be read."""

    RAN = "ran"
    FAILED = "failed"
    SKIPPED = "skipped"
    LISTED = "listed"


@dataclass(frozen=True)
class Row:
    """One entry, or one module that did not import or could not be read, whose ``name`` is
    None."""

    module: str
    name: str | None
    status: Status
    seed: Mapping[str, object] | None = None
    reason: str | None = None
    # the entry's pyct run summary line, as it printed it
    run: Mapping[str, object] | None = None

    @property
    def order(self) -> tuple[str, str]:
        """Module name, then entry name, in Python's string order; a module's own row first."""
        return (self.module, self.name or "")


def row_line(row: Row) -> str:
    """One row as its JSON line."""
    return json.dumps(
        {
            "module": row.module,
            "name": row.name,
            "status": row.status.value,
            "seed": row.seed,
            "reason": row.reason,
            "run": row.run,
        }
    )


def told(row: Row) -> str | None:
    """The stderr line after a row, or None for a listed one, which says nothing more."""
    if row.status is Status.RAN:
        return f"ran {_named(row)}: {_run_told(row.run or {})}"
    if row.status is Status.LISTED:
        return None
    return f"{row.status.value} {_named(row)}: {row.reason}"


def running(row: Row, number: int, count: int) -> str:
    """The stderr line before an entry's run: the entry, its seed, and how far the sweep is."""
    return f"running {_named(row)} {json.dumps(row.seed)} ({number} of {count})"


def count(rows: Iterable[Row], status: Status) -> int:
    """How many rows have ``status``."""
    return sum(1 for row in rows if row.status is status)


def covered_and_total(
    run: Mapping[str, object],
) -> tuple[Mapping[str, list[int]], Mapping[str, int]]:
    """The lines a run's summary line says it covered, and the line counts, for each file."""
    return cast("Mapping[str, list[int]]", run["covered"]), cast("Mapping[str, int]", run["total"])


def _run_told(run: Mapping[str, object]) -> str:
    covered, total = covered_and_total(run)
    lines = sum(len(lines) for lines in covered.values())
    return f"covered {lines} of {sum(total.values())} lines, stopped: {run['stopped']}"


def _named(row: Row) -> str:
    """The entry as ``pyct run`` names it, or the module alone on a module's row."""
    return row.module if row.name is None else f"{row.module}::{row.name}"
