"""The readable trace, the stderr half of what a run says: each input's lines, then how it ended."""

import json

from pyct.core.branch import Branch, Expression, Site
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure
from pyct.results.record import Aim, DowngradeCount, InputRecord, Miss, RunResult, Stop


def render_trace(record: InputRecord, coverage: Coverage) -> str:
    """One fact per line, each line ending in a newline: head, forks, coverage, end, losses."""
    lines = _head(record)
    lines += [_fork(branch) for branch in record.forks]
    lines += [
        f"covered {len(covered)} of {coverage.total[file]} lines in {file}"
        for file, covered in coverage.covered.items()
    ]
    lines += _ended(record.failure)
    lost = ", ".join(_downgrade(entry) for entry in record.downgrades)
    lines.append(f"downgrades {lost or 'none'}")
    return "".join(f"{line}\n" for line in lines)


def render_stop(result: RunResult) -> str:
    """What the run missed and why it ended, after the last input's trace.

    One ``missed`` line per fork the solver gave no input for, then the
    ``stopped`` line. What a failed solver said goes indented under it.
    """
    lines = [_miss(miss) for miss in result.misses]
    lines += _stopped(result.stopped)
    return "".join(f"{line}\n" for line in lines)


def _miss(miss: Miss) -> str:
    """The fork the solver was asked about, and the answer that gave no input."""
    return f"missed {_site(miss.site)} {miss.why.value}"


def _stopped(stop: Stop) -> list[str]:
    """Why the run ended, in words. A detail follows, indented under the line."""
    lines = [f"stopped: {stop.kind.value}"]
    if stop.detail is not None:
        lines += [f"    {line}" for line in stop.detail.splitlines()]
    return lines


def _head(record: InputRecord) -> list[str]:
    """Where the input came from, and, when the solver aimed it, whether it landed."""
    lines = [f"{record.source.value} {json.dumps(record.args)}"]
    if record.aim is None:
        return lines
    lines.append(_aim(record.aim))
    at = record.mismatch_at
    lines.append("reached" if at is None else _left_the_plan(record.forks, at))
    return lines


def _left_the_plan(forks: tuple[Branch, ...], at: int) -> str:
    """Where the path left the plan, and what the run hit at that position.

    A position with no fork means the run stopped forking before the plan
    ran out: a raise, an exit, the deadline, or a concrete value pyct lost
    track of. No int-only fixture reaches that through the command line
    today, which is why only a unit test covers it.
    """
    left = f"left the plan at position {at}"
    if at >= len(forks):
        return f"{left}, no fork there"
    return f"{left}, hit {_site(forks[at].site)}"


def _aim(aim: Aim) -> str:
    """The fork the input was solved for, and where on the path it sits."""
    return f"aim {_site(aim.site)} at position {aim.position}"


def _downgrade(entry: DowngradeCount) -> str:
    """One call is its bare name; a run of them carries how many."""
    return entry.name if entry.count == 1 else f"{entry.name} ×{entry.count}"


def _fork(branch: Branch) -> str:
    """Where it forked, what it tested, and which side it took."""
    side = "taken" if branch.taken else "not taken"
    return f"fork {_site(branch.site)}  {_infix(branch.expression)}  {side}"


def _site(site: Site) -> str:
    """Where a fork is, written the way every line that names one writes it."""
    return f"{site.file}:{site.line}:{site.col}"


def _ended(failure: Failure | None) -> list[str]:
    """How it ended, in words. A traceback follows, indented under the line."""
    if failure is None:
        return ["ended returned"]
    kind = failure.kind.value.replace("_", " ")
    lines = [f"ended {kind}: {failure.detail}"]
    if failure.traceback is not None:
        lines += [f"    {line}" for line in failure.traceback.splitlines()]
    return lines


def _infix(expression: Expression) -> str:
    """The condition the way a person writes it, whatever the operator is.

    Operator first is how the expression is stored, so one operand reads
    ``op a`` and the rest read as ``a op b``, joined by the operator.
    """
    if not isinstance(expression, list):
        return expression if isinstance(expression, str) else repr(expression)
    operator, *operands = expression
    written = [_operand(operand) for operand in operands]
    if len(written) == 1:
        return f"{operator} {written[0]}"
    return f" {operator} ".join(written)


def _operand(expression: Expression) -> str:
    """A condition inside a condition gets parentheses; a leaf stands on its own."""
    written = _infix(expression)
    return f"({written})" if isinstance(expression, list) else written
