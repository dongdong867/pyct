"""The one JSON line per input that other tools read from stdout."""

import json

from pyct.core.branch import Branch
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure
from pyct.results.record import DowngradeCount, InputRecord


def render(record: InputRecord, coverage: Coverage) -> str:
    """One line, no newline inside; line numbers sorted so the text is stable."""
    payload = {
        "args": record.args,
        "forks": [_fork(branch) for branch in record.forks],
        "covered": {file: sorted(lines) for file, lines in coverage.covered.items()},
        "total": dict(coverage.total),
        "failure": _failure(record.failure),
        "downgrades": [_downgrade(entry) for entry in record.downgrades],
    }
    return json.dumps(payload)


def _downgrade(entry: DowngradeCount) -> dict[str, object]:
    """One dunder that dropped the condition, and how many calls in a row did."""
    return {"name": entry.name, "count": entry.count}


def _failure(failure: Failure | None) -> dict[str, str] | None:
    """How it ended, or ``None`` when the call returned."""
    if failure is None:
        return None
    return {"kind": failure.kind.value, "detail": failure.detail}


def _fork(branch: Branch) -> dict[str, object]:
    """One fork: where it is, which side the input took, and what it tested."""
    return {
        "file": branch.site.file,
        "line": branch.site.line,
        "col": branch.site.col,
        "taken": branch.taken,
        "expression": branch.expression,
    }
