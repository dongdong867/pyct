"""The readable trace of one input, the stderr half of what a run says."""

import json

from pyct.core.branch import Branch, Expression
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure
from pyct.results.record import DowngradeCount, InputRecord


def render_trace(record: InputRecord, coverage: Coverage) -> str:
    """One fact per line, each line ending in a newline: seed, forks, coverage, end, losses."""
    lines = [f"seed {json.dumps(record.args)}"]
    lines += [_fork(branch) for branch in record.forks]
    lines += [
        f"covered {len(covered)} of {coverage.total[file]} lines in {file}"
        for file, covered in coverage.covered.items()
    ]
    lines += _ended(record.failure)
    lost = ", ".join(_downgrade(entry) for entry in record.downgrades)
    lines.append(f"downgrades {lost or 'none'}")
    return "".join(f"{line}\n" for line in lines)


def _downgrade(entry: DowngradeCount) -> str:
    """One call is its bare name; a run of them carries how many."""
    return entry.name if entry.count == 1 else f"{entry.name} ×{entry.count}"


def _fork(branch: Branch) -> str:
    """Where it forked, what it tested, and which side it took."""
    site = branch.site
    side = "taken" if branch.taken else "not taken"
    return f"fork {site.file}:{site.line}:{site.col}  {_infix(branch.expression)}  {side}"


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
