"""What bounds a sweep, what a finished sweep holds, and the lines that close its output.

The summary line closes stdout; a tool tells it from a row by ``swept``.
The closing lines end stderr.
"""

import json
import platform
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from enum import StrEnum

from pyct.sweep.rows import Row, Status, count


@dataclass(frozen=True)
class SweepLimits:
    """The limits each entry's ``pyct run`` gets, the bound on the whole sweep, and the grace.

    The defaults are the compare tool's, so a sweep row and a compare row of
    one entry run under the same limits. ``total_budget`` None is no bound on
    the whole sweep. ``grace`` is not a flag: it is both the limit on one
    module's import while listing and how long an entry's run may go on past
    its budget before sweep stops it; ``pyct run`` ends within a second of its
    deadline, so the grace mostly covers the import, which the budget does
    not count.
    """

    budget: float = 30.0
    plateau: int = 5
    solver_timeout: float = 10.0
    total_budget: float | None = None
    grace: float = 60.0


class SweepStop(StrEnum):
    """Why a sweep stopped."""

    DONE = "done"
    TOTAL_BUDGET_SPENT = "total budget spent"
    LISTED = "listed"


@dataclass(frozen=True)
class SweepResult:
    """A finished sweep: its rows in print order, why it stopped, and the coverage they sum.

    ``covered`` is, for each file, every line any entry's run covered, and
    ``total`` the line count the runs give. ``cvc5`` is its version, or None
    when it was not looked for or did not say.
    """

    package: str
    rows: tuple[Row, ...]
    stopped: SweepStop
    limits: SweepLimits
    covered: Mapping[str, frozenset[int]] = field(default_factory=dict)
    total: Mapping[str, int] = field(default_factory=dict)
    cvc5: str | None = None


def summary_line(result: SweepResult) -> str:
    """The line that closes stdout: the counts, the coverage summed by file, and the limits."""
    limits = {name: value for name, value in asdict(result.limits).items() if name != "grace"}
    environment = {
        "python": platform.python_version(),
        "cvc5": result.cvc5,
        "platform": platform.platform(),
    }
    payload = {"swept": result.package, "stopped": result.stopped.value}
    payload |= {status.value: count(result.rows, status) for status in Status}
    payload |= {
        "covered": {file: sorted(lines) for file, lines in sorted(result.covered.items())},
        "total": dict(sorted(result.total.items())),
        "limits": limits,
        "environment": environment,
    }
    return json.dumps(payload)


def closing(result: SweepResult) -> str:
    """The stderr lines that end a sweep: what was found, the counts, the coverage, and why it
    stopped. A listing ran nothing, so it has no coverage line."""
    rows = result.rows
    lines = (
        []
        if any(row.name is not None for row in rows)
        else [f"found no entries in {result.package}"]
    )
    skipped, failed = count(rows, Status.SKIPPED), count(rows, Status.FAILED)
    if result.stopped is SweepStop.LISTED:
        listed = count(rows, Status.LISTED)
        lines.append(
            f"listed {len(rows)} entries: {listed} listed, {skipped} skipped, {failed} failed"
        )
    else:
        ran = count(rows, Status.RAN)
        lines.append(f"swept {len(rows)} entries: {ran} ran, {skipped} skipped, {failed} failed")
        lines.append(_covered_told(result))
    lines.append(f"stopped: {result.stopped.value}")
    return "".join(f"{line}\n" for line in lines)


def _covered_told(result: SweepResult) -> str:
    lines = sum(len(lines) for lines in result.covered.values())
    files = len(result.total)
    named = "1 file" if files == 1 else f"{files} files"
    return f"covered {lines} of {sum(result.total.values())} lines in {named}"
