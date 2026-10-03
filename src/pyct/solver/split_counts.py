"""What a split's count is on the input whose path this is, and what the path's forks with plain
ints say it may be: c*, which a count that meets anything else is (see ``split_lists``).

The count this run produced is read back from the input's own values: the string a split
splits is worked out as Python worked it out, through slices, indexes, joins, repeats and str
methods with plain operands, down to the arguments. A fork that compares a count with a plain
int, through the lists the encoder reads the same way (a slice with plain bounds, a list
display joined on, and `+`, `-` or `*` with a plain int), says which
counts take its side; c* is the one nearest the input's own that every such fork allows.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from pyct.core.branch import Branch, Expression
from pyct.core.str_splits import LISTED_SPLITS, WORKED_METHODS, a_split_s_list
from pyct.solver.list_terms import FALSE, SUM_DEPTH, TRUE, both, negated
from pyct.solver.literals import plain_operand

# each compare on two ints, as Python takes it
_COMPARES: Mapping[str, Callable[[int, int], bool]] = {
    "<": lambda left, right: left < right,
    "<=": lambda left, right: left <= right,
    ">": lambda left, right: left > right,
    ">=": lambda left, right: left >= right,
    "==": lambda left, right: left == right,
    "!=": lambda left, right: left != right,
}

# plain arithmetic on a count with a plain int, as Python takes it
_ARITHMETIC: Mapping[str, Callable[[int, int], int]] = {
    "+": lambda left, right: left + right,
    "-": lambda left, right: left - right,
    "*": lambda left, right: left * right,
}

# how far from the input's own count c* is looked for: past it, the path's compares with plain
# ints rule out every count near the input's, and c* stays the input's own
FARTHEST = 10_000

# the longest string or list worked out from the input's values: a repeat past it is not read
_LONGEST = 1_000_000

# what a side of a compare is: the split whose count it reads, and its value at each count
type Counting = tuple[list[Expression], Callable[[int], int]]


def condition(fork: Branch) -> tuple[list[Expression], Callable[[int], bool]] | None:
    """The split a fork compares the count of, through the lists and arithmetic the encoder
    reads, with a plain int, and whether a count takes the fork's side; None for any other."""
    expression = fork.expression
    if not isinstance(expression, list) or len(expression) != 3:
        return None
    test = _COMPARES.get(str(expression[0]))
    left, right = expression[1], expression[2]
    if test is None or (type(left) is int) == (type(right) is int):
        return None
    side = counting(left) if type(right) is int else counting(right)
    if side is None:
        return None
    split, value = side
    number = right if type(right) is int else left
    assert isinstance(number, int)
    if type(right) is int:
        return split, lambda at: test(value(at), number) is fork.taken
    return split, lambda at: test(number, value(at)) is fork.taken


def counting(part: Expression, depth: int = SUM_DEPTH) -> Counting | None:
    """A side of a compare that reads one split's count: a list's length (``measured``), or
    one through `+`, `-` or `*` with a plain int, nested at most ``depth`` deep, and its value
    at each count; None for any other side."""
    if not isinstance(part, list) or len(part) not in (2, 3):
        return None
    if part[0] == "len" and len(part) == 2:
        return measured(part[1])
    combine = _ARITHMETIC.get(str(part[0]))
    if combine is None or len(part) != 3 or depth == 0:
        return None
    left, right = part[1], part[2]
    if type(right) is int and (side := counting(left, depth - 1)) is not None:
        split, value = side
        return split, lambda at: combine(value(at), right)
    if type(left) is int and (side := counting(right, depth - 1)) is not None:
        split, value = side
        return split, lambda at: combine(left, value(at))
    return None


def measured(form: Expression) -> Counting | None:
    """A split's list as the encoder writes it exactly (``str_splits.a_split_s_list``), and its
    length at each count: the split's list, a slice with plain bounds, a slice of one, or one
    with a list display joined on; None for any other list."""
    if not a_split_s_list(form):
        return None
    assert isinstance(form, list)
    return _length(form)


def _length(form: list[Expression]) -> Counting:
    """The split a form `a_split_s_list` takes is built from, and the form's length at each
    of its counts."""
    head, operands = form[0], form[1:]
    if head in LISTED_SPLITS:
        return form, lambda at: at
    listed = operands[0]
    if head == "[:]":
        assert isinstance(listed, list)
        split, length = _length(listed)
        window = slice(*operands[1:])
        return split, lambda at: windowed((window,), length(at))
    shown = next(part for part in operands if isinstance(part, list) and part[:1] == ["[,]"])
    listed = next(part for part in operands if part is not shown)
    assert isinstance(listed, list) and isinstance(shown, list)
    split, length = _length(listed)
    return split, lambda at: length(at) + len(shown) - 1


def windows_past(past: Callable[[int], str], windows: Sequence[slice], number: int) -> str:
    """That a list cut from a split's by ``windows``, one after another, holds more items than
    ``number``: for each run of counts that make it that long, the split holding at least the
    first and no more than the last, or open past the last. Past ``bend`` every bound counts
    from where it does at any count, so the length is a line in the count there, and its run
    is worked out, not counted one by one."""
    if number < 0:
        return TRUE
    bend = 2 + sum(
        abs(bound) for window in windows for bound in (window.start, window.stop) if bound
    )
    runs = _runs([windowed(windows, at) > number for at in range(bend + 1)])
    rising = windowed(windows, bend + 1) - windowed(windows, bend)
    tail = _past_the_bend(windowed(windows, bend), rising, bend, number)
    if tail is not None and runs and runs[-1][1] == bend:
        tail = (runs.pop()[0], tail[1])
    runs += [tail] if tail is not None else []
    written = [
        past(first - 1) if last is None else both(past(first - 1), negated(past(last)))
        for first, last in runs
    ]
    if not written:
        return FALSE
    return written[0] if len(written) == 1 else f"(or {' '.join(written)})"


def _runs(long: list[bool]) -> list[tuple[int, int | None]]:
    """Each run of positions that hold, its first and its last."""
    runs: list[tuple[int, int | None]] = []
    for at, inside in enumerate(long):
        if inside and (at == 0 or not long[at - 1]):
            runs.append((at, at))
        elif inside:
            runs[-1] = (runs[-1][0], at)
    return runs


def _past_the_bend(
    length: int, rising: int, bend: int, number: int
) -> tuple[int, int | None] | None:
    """The run of counts past ``bend`` whose length, ``length`` at ``bend`` and ``rising`` more
    for each count past it, is more than ``number``; None for none. A slice that counts its
    start from the end and its stop from the start shrinks as the count grows, but to nothing
    before ``bend``, so past it a length only grows or stays."""
    assert rising >= 0
    if rising == 0:
        return (bend + 1, None) if length > number else None
    return bend + max(1, (number - length) // rising + 1), None


def windowed(windows: Sequence[slice], count: int) -> int:
    """How many items a list of ``count`` items holds once cut by ``windows`` in turn."""
    for window in windows:
        count = len(range(*window.indices(count)))
    return count


def input_value(part: Expression, given: Callable[[Expression], object]) -> object:
    """A part's value in the input whose path this is, worked out as Python worked it out from
    a name's or a literal's (``str_splits.worked_out`` says which parts core lets through);
    None where a part's is not known."""
    try:
        return _worked_out(part, given, {})
    except (ArithmeticError, LookupError, TypeError, ValueError, RecursionError):
        return None


def _worked_out(
    part: Expression, given: Callable[[Expression], object], memo: dict[int, object]
) -> object:
    held = given(part)
    if held is not None or not isinstance(part, list):
        return held if held is not None else plain_operand(part)
    if id(part) in memo:
        return memo[id(part)]
    head, *operands = part
    values = [_worked_out(operand, given, memo) for operand in operands]
    value = _applied(str(head), values)
    if isinstance(value, str | list) and len(value) > _LONGEST:
        raise ValueError("a value past the longest worked out")
    memo[id(part)] = value
    return value


def _applied(head: str, values: list[object]) -> object:
    """``head`` on values, as ``str_splits.worked_out`` lets core write it: a slice, an index,
    a join, a repeat, a split or a `WORKED_METHODS` call."""
    first = values[0]
    if head == "[:]" and isinstance(first, str | list):
        bounds = [bound if isinstance(bound, int) else None for bound in values[1:]]
        picked = [first[at] for at in range(*slice(*bounds).indices(len(first)))]
        return "".join(str(item) for item in picked) if isinstance(first, str) else picked
    if head == "[]" and isinstance(first, str | list) and isinstance(values[1], int):
        return first[values[1]]
    if head in ("+", "*"):
        if head == "*" and _too_long(values):
            raise ValueError("a repeat past the longest worked out")
        left, right = values
        return left + right if head == "+" else left * right  # pyrefly: ignore[unsupported-operation]
    if isinstance(first, str) and (head in WORKED_METHODS or head in LISTED_SPLITS):
        return getattr(str, head)(first, *values[1:])
    raise ValueError(f"no value worked out for {head}")


def _too_long(values: list[object]) -> bool:
    """Whether a repeat of a string or a list would hold more than ``_LONGEST`` items."""
    times = [value for value in values if type(value) is int]
    held = [value for value in values if isinstance(value, str | list)]
    return bool(times and held) and len(held[0]) * times[0] > _LONGEST
