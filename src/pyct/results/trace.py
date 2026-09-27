"""The readable trace, the stderr half of what a run says: each input's lines, then how it ended."""

import json
import keyword
from collections.abc import Sequence

from pyct.core.branch import Branch, Expression, Site
from pyct.results.coverage import Coverage
from pyct.results.failure import Failure
from pyct.results.printed import CUT, printed_forks
from pyct.results.record import (
    Aim,
    DowngradeCount,
    InputRecord,
    Miss,
    RunResult,
    SolverCounts,
    Stop,
)


def render_trace(
    record: InputRecord, coverage: Coverage, printed: Sequence[Expression] | None = None
) -> str:
    """One fact per line, each line ending in a newline: head, forks, coverage, end, losses.

    ``printed`` is each fork's expression as `printed_forks` cut it, for a
    caller that cut them once for the trace and the stdout line alike.
    """
    expressions = printed_forks(record.forks) if printed is None else printed
    lines = _head(record)
    lines += [_fork(*pair) for pair in zip(record.forks, expressions, strict=True)]
    lines += _coverage(coverage)
    lines += _ended(record.failure)
    lost = ", ".join(_downgrade(entry) for entry in record.downgrades)
    lines.append(f"downgrades {lost or 'none'}")
    return _written(lines)


def render_miss(miss: Miss) -> str:
    """The fork the solver was asked about, and the answer that gave no input.

    Its own line rather than part of the summary, so a caller can print it
    the moment the answer comes in, before the next input's trace.
    """
    return _written([f"missed {_site(miss.site)} {miss.why.value}"])


def render_stop(result: RunResult) -> str:
    """What the run added up to and why it ended, after the last trace.

    The summary starts at its first ``covered`` line and ends on the
    ``stopped`` line, with an ``uncovered`` line in between for each file
    that has lines left; what a failed solver said goes indented under the
    ``stopped`` line. A miss is not here: it printed as its answer came in.
    """
    lines = _summary(result)
    lines += _stopped(result.stopped)
    return _written(lines)


def _written(lines: list[str]) -> str:
    """One fact per line, each line ending in a newline. This is the whole trace's shape."""
    return "".join(f"{line}\n" for line in lines)


def _summary(result: RunResult) -> list[str]:
    """What the whole run covered, what the solver answered, and what it left behind."""
    coverage = result.coverage
    lines = [*_coverage(coverage), _solver(result.solver)]
    lines += [_uncovered(file, left) for file, left in coverage.uncovered.items() if left]
    return lines


def _coverage(coverage: Coverage) -> list[str]:
    """How much of each file was covered, one line per file, in the map's order."""
    return [
        f"covered {len(covered)} of {coverage.total[file]} lines in {file}"
        for file, covered in coverage.covered.items()
    ]


def _solver(counts: SolverCounts) -> str:
    """What the solver answered over the run, one count per kind of answer."""
    return (
        f"solver: {counts.sat} sat, {counts.unsat} unsat, "
        f"{counts.unknown} unknown, {counts.timeout} timeout"
    )


def _uncovered(file: str, lines: frozenset[int]) -> str:
    """The lines of one file no input ran, ascending. A file with none gets no line at all."""
    numbers = ", ".join(str(line) for line in sorted(lines))
    return f"uncovered {numbers} in {file}"


def _indented(detail: str | None) -> list[str]:
    """The lines of a detail, under the line it belongs to. No detail is no lines."""
    return [] if detail is None else [f"    {line}" for line in detail.splitlines()]


def _stopped(stop: Stop) -> list[str]:
    """Why the run ended, in words. A detail follows, indented under the line."""
    return [f"stopped: {stop.reason}", *_indented(stop.detail)]


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
    track of.
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


def _fork(branch: Branch, expression: Expression) -> str:
    """Where it forked, what it tested, cut to the cap as the stdout line cuts it, and the side."""
    side = "taken" if branch.taken else "not taken"
    return f"fork {_site(branch.site)}  {_infix(expression)}  {side}"


def _site(site: Site) -> str:
    """Where a fork is, written the way every line that names one writes it."""
    return f"{site.file}:{site.line}:{site.col}"


def _ended(failure: Failure | None) -> list[str]:
    """How it ended, in words. A traceback follows, indented under the line."""
    if failure is None:
        return ["ended returned"]
    kind = failure.kind.value.replace("_", " ")
    return [f"ended {kind}: {failure.detail}", *_indented(failure.traceback)]


# a part as the fork line writes it, and whether it stands alone as an operand: a leaf does,
# and so does a part Python writes around its operands
type _Text = tuple[str, bool]


def _infix(expression: Expression) -> str:
    """The condition the way a person writes it, whatever the operator is.

    Operator first is how the expression is stored, so one operand reads
    ``op a`` and the rest read as ``a op b``, joined by the operator, but for
    what Python writes around its operands (see `_around`). Each part is
    written after its operands, on a stack of its own rather than Python's,
    so a condition nested past Python's recursion limit is written too.
    """
    written: list[_Text] = []
    stack: list[tuple[Expression, bool]] = [(expression, False)]
    while stack:
        part, operands_written = stack.pop()
        if not isinstance(part, list):
            written.append((part if isinstance(part, str) else repr(part), True))
        elif operands_written:
            first = len(written) - (len(part) - 1)
            written[first:] = [_text(part, written[first:])]
        else:
            stack.append((part, True))
            # the leftmost operand on top, so the operands are written in their order
            stack.extend((operand, False) for operand in reversed(part[1:]))
    return written[0][0]


def _text(expression: list[Expression], operands: list[_Text]) -> _Text:
    """One condition, written from its operands, each already written."""
    around = _around(expression, operands)
    if around is not None:
        return around, True
    operator = expression[0]
    parts = [_operand(operand) for operand in operands]
    if len(parts) == 1:
        return f"{operator} {parts[0]}", False
    return f" {operator} ".join(parts), False


# the builtins a fork line writes as Python calls them: `len(s)`
_CALLED = ("len",)


def _around(expression: list[Expression], operands: list[_Text]) -> str | None:
    """A condition Python writes around its operands, or None for one it writes between them.

    An index reads ``s[i]`` and a slice ``s[i:j]``, a missing bound left out.
    A builtin in `_CALLED` reads ``len(s)``, and a named head with arguments
    reads as Python calls a method, ``a.name(b)``. A part cut from a long
    expression reads ``...(N nodes)``, and ``...(? nodes)`` when its count is
    ``null``. Each binds tighter than any operator, so none needs parentheses
    of its own.
    """
    head = expression[0]
    texts = [text for text, _ in operands]
    if head == CUT:
        return f"...({'?' if expression[1] is None else texts[0]} nodes)"
    if head == "[]" or head == "[:]":
        bounds = zip(expression[2:], texts[1:], strict=True)
        written = ":".join("" if position is None else text for position, text in bounds)
        return f"{_operand(operands[0])}[{written}]"
    if head in _CALLED:
        return f"{head}({', '.join(texts)})"
    if _is_named_with_arguments(expression):
        return f"{_operand(operands[0])}.{head}({', '.join(texts[1:])})"
    return None


def _is_named_with_arguments(expression: list[Expression]) -> bool:
    """Whether a condition is a named head on a receiver and at least one argument.

    A name is an identifier that is not a keyword, so ``in`` stays an
    operator Python writes between its operands. A named head on one
    operand, such as ``abs``, keeps the ``op a`` it always had.
    """
    head = expression[0]
    return (
        isinstance(head, str)
        and head.isidentifier()
        and not keyword.iskeyword(head)
        and len(expression) > 2
    )


def _operand(written: _Text) -> str:
    """A condition inside a condition gets parentheses; a leaf stands alone.

    So does a condition Python writes around its operands, ``s[0]`` or
    ``a.name(b)``.
    """
    text, alone = written
    return text if alone else f"({text})"
