"""The JSON lines other tools read from stdout: one per input, then one for the run."""

import json
from collections.abc import Mapping

from pyct.core.branch import Branch
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure
from pyct.results.record import (
    Aim,
    DowngradeCount,
    Environment,
    InputRecord,
    Miss,
    RunResult,
    SolverCounts,
)


def render(record: InputRecord, coverage: Coverage) -> str:
    """One line, no newline inside; line numbers sorted so the text is stable."""
    payload = {
        "args": record.args,
        "forks": [_fork(branch) for branch in record.forks],
        "covered": _numbers(coverage.covered),
        "total": dict(coverage.total),
        "failure": _failure(record.failure),
        "downgrades": [_downgrade(entry) for entry in record.downgrades],
        "source": record.source.value,
        "aim": _aim(record.aim),
        "mismatch_at": record.mismatch_at,
    }
    return json.dumps(payload)


def render_summary(result: RunResult) -> str:
    """The line that closes stdout, one line for the whole run.

    A tool tells it from an input line by ``stopped``, which no input line
    carries. The coverage is written the way an input line writes its own,
    and ``uncovered`` is keyed like ``total``: a file with nothing left over
    carries an empty list rather than dropping out.
    """
    payload = {
        "stopped": result.stopped.reason,
        "inputs": result.inputs,
        "solver": _counts(result.solver),
        "misses": [_miss(miss) for miss in result.misses],
        "covered": _numbers(result.coverage.covered),
        "total": dict(result.coverage.total),
        "uncovered": _numbers(result.coverage.uncovered),
        "environment": _environment(result.environment),
    }
    return json.dumps(payload)


def _numbers(by_file: Mapping[str, frozenset[int]]) -> dict[str, list[int]]:
    """One map of line numbers, sorted so the text is the same on every run."""
    return {file: sorted(lines) for file, lines in by_file.items()}


def _counts(counts: SolverCounts) -> dict[str, int]:
    """What the solver answered, one key per kind of answer."""
    return {
        "sat": counts.sat,
        "unsat": counts.unsat,
        "unknown": counts.unknown,
        "timeout": counts.timeout,
    }


def _environment(environment: Environment) -> dict[str, object]:
    """What the run ran in. ``cvc5`` is null when the probe gave nothing readable."""
    return {
        "python": environment.python,
        "cvc5": environment.cvc5,
        "platform": environment.platform,
    }


def _miss(miss: Miss) -> dict[str, object]:
    """One fork the solver gave no input for: where it is, and what it answered."""
    return {
        "file": miss.site.file,
        "line": miss.site.line,
        "col": miss.site.col,
        "why": miss.why.value,
    }


def _aim(aim: Aim | None) -> dict[str, object] | None:
    """The fork the input was solved for, or ``None`` when nothing was aimed at."""
    if aim is None:
        return None
    return {
        "file": aim.site.file,
        "line": aim.site.line,
        "col": aim.site.col,
        "position": aim.position,
    }


def _downgrade(entry: DowngradeCount) -> dict[str, object]:
    """One method or dunder that dropped the condition, and how many calls in a row did."""
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
