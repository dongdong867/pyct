"""The JSON lines other tools read from stdout: one per input, then one for the run."""

import json
from collections.abc import Mapping

from pyct.core.branch import Branch, Expression
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure
from pyct.results.printed import CUT, PrintedForks, printed_forks
from pyct.results.record import (
    Aim,
    DowngradeCount,
    Environment,
    InputRecord,
    Miss,
    RunResult,
    SolverCounts,
)
from pyct.results.why_render import why_json


def render(record: InputRecord, coverage: Coverage, printed: PrintedForks | None = None) -> str:
    """One line, no newline inside; line numbers sorted so the text is stable.

    ``printed`` is each fork's expression as `printed_forks` cut it, for a
    caller that cut them once for this line and the trace alike.
    """
    expressions = (printed_forks(record.forks) if printed is None else printed).expressions
    head = json.dumps({"args": record.args})
    rest = {
        "covered": _numbers(coverage.covered),
        "total": dict(coverage.total),
        "failure": _failure(record.failure),
        "downgrades": [_downgrade(entry) for entry in record.downgrades],
        "source": record.source.value,
        "aim": _aim(record.aim),
        "mismatch_at": record.mismatch_at,
    }
    # as json.dumps writes the whole line, with the forks written here, each site's text once
    forks = _forks(record.forks, expressions)
    return f'{head[:-1]}, "forks": [{forks}], {json.dumps(rest)[1:]}'


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
        "why_uncovered": [why_json(entry) for entry in result.why_uncovered],
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
        "isolated": environment.isolated,
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
    """One method or dunder that dropped the condition, how many calls in a row did, and where."""
    site = entry.site
    return {
        "name": entry.name,
        "count": entry.count,
        "file": site.file,
        "line": site.line,
        "col": site.col,
    }


def _failure(failure: Failure | None) -> dict[str, str] | None:
    """How it ended, or ``None`` when the call returned."""
    if failure is None:
        return None
    return {"kind": failure.kind.value, "detail": failure.detail}


def _forks(forks: tuple[Branch, ...], expressions: tuple[Expression, ...]) -> str:
    """The forks as json.dumps writes a list of `_fork`'s dicts, without the brackets.

    A site's text, with the side, is made once however many forks name it,
    since a loop's path names one site on every pass. The forks hold their
    sites while this runs, so no id is reused.
    """
    at: dict[tuple[int, bool], str] = {}
    written: list[str] = []
    for branch, expression in zip(forks, expressions, strict=True):
        key = (id(branch.site), branch.taken)
        head = at.get(key)
        if head is None:
            head = at[key] = json.dumps(_fork(branch, None)).removesuffix("null}")
        written.append(f"{head}{_expression(expression)}}}")
    return ", ".join(written)


def _expression(expression: Expression) -> str:
    """An expression as json.dumps writes it. A cut part is written here, which is most forks'
    expression on a long line."""
    if type(expression) is list and len(expression) == 2 and expression[0] == CUT:
        count = expression[1]
        if count is None:
            return '["...", null]'
        if type(count) is int:
            return f'["...", {count}]'
    return json.dumps(expression)


def _fork(branch: Branch, expression: Expression) -> dict[str, object]:
    """One fork: where it is, which side the input took, and what it tested, cut to the cap."""
    return {
        "file": branch.site.file,
        "line": branch.site.line,
        "col": branch.site.col,
        "taken": branch.taken,
        "expression": expression,
    }
