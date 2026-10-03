"""What a split's count is on the input whose path this is, and what the path's forks with plain
ints say it may be: c*, which a count that meets anything else is (see ``split_lists``).

The count this run produced is read back from the input's own values: the string a split
splits is worked out as Python worked it out, through slices, indexes, joins, repeats and str
methods with plain operands, down to the arguments. A fork that compares a count with a plain
int, through the lists the encoder reads the same way (a slice with plain bounds, a list
display joined on, a repeat by a plain int, and `+`, `-` or `*` with a plain int), says which
counts take its side; c* is the one nearest the input's own that every such fork allows.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence

from pyct.core.branch import Branch, Expression
from pyct.core.str_splits import LISTED_SPLITS
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
        return measured(part[1], depth)
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


def measured(form: Expression, depth: int = SUM_DEPTH) -> Counting | None:
    """A list built from one split's list as the encoder reads its length, and that length at
    each count: the split's list, a slice with plain bounds, a list display joined on either
    side, or a repeat by a plain int, nested at most ``depth`` deep; None for any other."""
    if not isinstance(form, list) or not form or depth < 0:
        return None
    head, operands = form[0], form[1:]
    if head in LISTED_SPLITS:
        return form, lambda at: at
    if head == "[:]" and all(bound is None or type(bound) is int for bound in operands[1:]):
        inner = measured(operands[0], depth - 1)
        window = slice(*operands[1:])
        return None if inner is None else _cut(inner, window)
    if head == "*" and len(operands) == 2:
        return _repeated(operands, depth)
    if head == "+" and len(operands) == 2:
        return _joined(operands, depth)
    return None


def _cut(inner: Counting, window: slice) -> Counting:
    split, length = inner
    return split, lambda at: windowed((window,), length(at))


def _repeated(operands: list[Expression], depth: int) -> Counting | None:
    listed, times = operands if type(operands[1]) is int else operands[::-1]
    if not isinstance(times, int) or isinstance(times, bool):
        return None
    inner = measured(listed, depth - 1)
    if inner is None:
        return None
    split, length = inner
    return split, lambda at: length(at) * max(times, 0)


def _joined(operands: list[Expression], depth: int) -> Counting | None:
    """Two lists joined, each a list display or a list built from the one split's."""
    sides = [side for part in operands if (side := _shown(part) or measured(part, depth - 1))]
    splits = [split for split, _ in sides if split]
    if len(sides) != 2 or not splits or any(split is not splits[0] for split in splits):
        return None
    (_, first), (_, second) = sides
    return splits[0], lambda at: first(at) + second(at)


def _shown(part: Expression) -> Counting | None:
    """A list display, which names no split, and its length at any count."""
    if not isinstance(part, list) or part[:1] != ["[,]"]:
        return None
    return [], lambda at: len(part) - 1


def cut_past(past: Callable[[int], str], longer: Callable[[int], bool], reach: int) -> str:
    """That a list cut from a split's by slices is long enough at the split's count, where
    ``longer`` says which counts make it so: for each run of such counts up to ``reach``, the
    split holding at least the first and no more than the last. Past ``reach`` every bound
    counts from where it does at any count, so the length grows, shrinks or stays with the
    count, and the last run is open there."""
    long = [longer(at) for at in range(reach + 1)]
    runs: list[str] = []
    first = TRUE
    for at, inside in enumerate(long):
        if inside and (at == 0 or not long[at - 1]):
            first = past(at - 1)
        if inside and (at == reach or not long[at + 1]):
            runs.append(first if at == reach else both(first, negated(past(at))))
    if not runs:
        return FALSE
    return runs[0] if len(runs) == 1 else f"(or {' '.join(runs)})"


def windows_past(past: Callable[[int], str], windows: Sequence[slice], number: int) -> str:
    """That a list cut from a split's by ``windows``, one after another, holds more items than
    ``number`` (``cut_past``)."""
    if number < 0:
        return TRUE
    bounds = [bound for window in windows for bound in (window.start, window.stop) if bound]
    reach = number + 2 + sum(abs(bound) for bound in bounds)
    return cut_past(past, lambda at: windowed(windows, at) > number, reach)


def windowed(windows: Sequence[slice], count: int) -> int:
    """How many items a list of ``count`` items holds once cut by ``windows`` in turn."""
    for window in windows:
        count = len(range(*window.indices(count)))
    return count


def input_value(part: Expression, given: Callable[[Expression], object]) -> object:
    """A part's value in the input whose path this is, worked out as Python worked it out: a
    name's or a literal's, or a slice, an index, a join, a repeat, a length, a display or a str
    method of parts worked out so; None where a part is none of these or not known."""
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
    """``head`` on values: a list or string operation, or a str method with its operands."""
    first = values[0] if values else None
    if head == "[,]":
        return values
    if head == "[:]" and isinstance(first, str | list):
        bounds = [bound if isinstance(bound, int) else None for bound in values[1:]]
        picked = [first[at] for at in range(*slice(*bounds).indices(len(first)))]
        return "".join(str(item) for item in picked) if isinstance(first, str) else picked
    index = values[1] if len(values) > 1 else None
    if head == "[]" and isinstance(first, str | list) and isinstance(index, int):
        return first[index]
    if head == "len" and isinstance(first, str | list):
        return len(first)
    if head in ("+", "*") and len(values) == 2:
        if head == "*" and _too_long(values):
            raise ValueError("a repeat past the longest worked out")
        left, right = values
        return left + right if head == "+" else left * right  # pyrefly: ignore[unsupported-operation]
    method = getattr(str, head, None) if isinstance(first, str) else None
    if callable(method) and not head.startswith("_"):
        return method(first, *values[1:])
    raise ValueError(f"no value worked out for {head}")


def _too_long(values: list[object]) -> bool:
    """Whether a repeat of a string or a list would hold more than ``_LONGEST`` items."""
    times = [value for value in values if type(value) is int]
    held = [value for value in values if isinstance(value, str | list)]
    return bool(times and held) and len(held[0]) * times[0] > _LONGEST
