"""The readable trace, the stderr half of what a run says: each input's lines, then how it ended."""

import json
import keyword
from collections.abc import Mapping, Sequence

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


# a part as the fork line writes it, and how tightly it binds as an operand, as `_BINARY` ranks
type _Text = tuple[str, int]

# how tightly Python's grammar binds what the fork line writes, loosest first. A head Python
# has no operator for, such as `abs`, is written `abs x` and binds looser than everything
_UNRANKED = 0
_COMPARES = 1
# a unary `-`, `+` or `~`, and a negative number, bind looser than `**` and tighter than `*`
_UNARY = 8
_POWER = 9
# a name, a literal that is not negative, and a part Python writes around its operands stand
# bare as any operand and as the base of `**`. Core puts a tracked value's expression where a
# method's receiver goes, never a literal, which Python would not read after a bare int
_ALONE = 10
_BINARY: Mapping[str, int] = {
    **dict.fromkeys(("in", "not in", "is", "is not", "<", "<=", ">", ">=", "==", "!="), _COMPARES),
    "|": 2,
    "^": 3,
    "&": 4,
    **dict.fromkeys(("<<", ">>"), 5),
    **dict.fromkeys(("+", "-"), 6),
    **dict.fromkeys(("*", "/", "//", "%"), 7),
    "**": _POWER,
}
_UNARY_OPERATORS = ("-", "+", "~")


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
            written.append(_leaf(part))
        elif operands_written:
            first = len(written) - (len(part) - 1)
            written[first:] = [_text(part, written[first:])]
        else:
            stack.append((part, True))
            # the leftmost operand on top, so the operands are written in their order
            stack.extend((operand, False) for operand in reversed(part[1:]))
    return written[0][0]


def _leaf(leaf: Expression) -> _Text:
    """A name or a literal as the line writes it. A negative number binds as a unary minus."""
    text = leaf if isinstance(leaf, str) else repr(leaf)
    return text, _UNARY if text.startswith("-") else _ALONE


def _text(expression: list[Expression], operands: list[_Text]) -> _Text:
    """One condition, written from its operands, each already written."""
    around = _around(expression, operands)
    if around is not None:
        return around, _ALONE
    operator = expression[0]
    if len(operands) == 1:
        return _prefixed(operator, operands[0])
    level = _BINARY.get(operator) if isinstance(operator, str) else None
    if level is None or len(operands) != 2:
        return f" {operator} ".join(_operand(part, _ALONE) for part in operands), _UNRANKED
    left, right = operands
    left_text = _operand(left, _least(level, right=False))
    return f"{left_text} {operator} {_operand(right, _least(level, right=True))}", level


def _prefixed(operator: Expression, operand: _Text) -> _Text:
    """A condition on one operand: a unary operator binds as Python's does, a named head not."""
    if operator in _UNARY_OPERATORS:
        return f"{operator} {_operand(operand, _UNARY)}", _UNARY
    return f"{operator} {_operand(operand, _ALONE)}", _UNRANKED


def _least(level: int, *, right: bool) -> int:
    """How tightly an operand must bind to stand bare beside a binary operator of this level.

    Most operators group from the left, so `x - 1 - 2` needs nothing and
    `x - (1 - 2)` keeps its parentheses. `**` groups from the right and takes
    a unary operand on its right, `x ** -y`. A compare never stands bare
    beside another, because two compares side by side are a chain.
    """
    if level == _COMPARES:
        return _COMPARES + 1
    if level == _POWER:
        return _UNARY if right else _ALONE
    return level + 1 if right else level


# the builtins a fork line writes as Python calls them: `len(s)`
_CALLED = ("len",)


def _around(expression: list[Expression], operands: list[_Text]) -> str | None:
    """A condition Python writes around its operands, or None for one it writes between them.

    An index reads ``s[i]`` and a slice ``s[i:j]``, a missing bound left out,
    and a key as the expression stores it, a string key in its Python quotes,
    ``config['port']``. A list display reads ``[x, 7]``.
    A builtin in `_CALLED` reads ``len(s)``, and a named head with arguments
    reads as Python calls a method, ``a.name(b)``. A part cut from a long
    expression reads ``...(N nodes)``, and ``...(? nodes)`` when its count is
    ``null``. Each binds tighter than any operator, so none needs parentheses
    of its own.
    """
    head = expression[0]
    texts = [text for text, _ in operands]
    if head == "[,]":
        return f"[{', '.join(texts)}]"
    if head == CUT:
        return f"...({'?' if expression[1] is None else texts[0]} nodes)"
    if head == "[]" or head == "[:]":
        bounds = zip(expression[2:], texts[1:], strict=True)
        written = ":".join("" if position is None else text for position, text in bounds)
        return f"{_operand(operands[0], _ALONE)}[{written}]"
    if head in _CALLED:
        return f"{head}({', '.join(texts)})"
    if _is_named_with_arguments(expression):
        return f"{_operand(operands[0], _ALONE)}.{head}({', '.join(texts[1:])})"
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


def _operand(written: _Text, least: int) -> str:
    """An operand, in parentheses unless it binds at least as tightly as its place needs.

    Only a name, a non-negative literal, and a condition Python writes around
    its operands, ``s[0]`` or ``a.name(b)``, stand bare as the base of
    ``**``. Only a name and such a condition stand bare as a receiver, which
    is all core puts there.
    """
    text, binding = written
    return text if binding >= least else f"({text})"
