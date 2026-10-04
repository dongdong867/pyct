"""A length range: the fewest and the most items a value holds on every input that takes the path.

Each tracked list, string and dict keeps one beside the length the solver sees
(decision forks-a-length-range-per-value-decides-its-checks-and-len-s-compares). It comes from
how the value was built and from the forks the path recorded on its length, never from the
million-item limit on an answer, so a check it proves holds on every input that records those
forks: such a check is a fact (``core.branch.Fact``), and any other a fork, which then narrows
the range. The int `len(x)` returns carries the range too, through `+`, `-` and `*` with a
plain int.

A range is ``(fewest, most)``; None is no bound, below or above. A length's fewest is never
below zero.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from pyct.core.branch import BranchSink, Expression
from pyct.core.values import forked, held

type Span = tuple[int | None, int | None]

# what a value holds when nothing about its length is known
UNKNOWN: Span = (0, None)


def exactly(count: int) -> Span:
    """The range of a value that holds ``count`` items on every input."""
    return (count, count)


def added(left: Span, right: Span) -> Span:
    """The range of two values joined end to end, or of a length plus an int."""
    return (_sum(left[0], right[0]), _sum(left[1], right[1]))


def scaled(span: Span, times: int) -> Span:
    """The range of a length times a plain int; a negative one swaps the ends."""
    fewest, most = (_times(span[0], times), _times(span[1], times))
    return (fewest, most) if times >= 0 else (most, fewest)


def repeated(span: Span, times: int) -> Span:
    """The range of a list or a string repeated a plain number of times: none at all for zero
    or fewer, as Python repeats it."""
    return exactly(0) if times <= 0 else scaled(span, times)


def sliced(span: Span, start: int | None, stop: int | None, step: int | None = None) -> Span:
    """The range of a slice with plain bounds and step, as Python's own clamp cuts it from a
    value of any length in ``span``."""
    cut = slice(start, stop, step)
    return over(span, lambda count: taken(cut, count), _breaks(start, stop), abs(step or 1))


def cut_out(span: Span, start: int | None, stop: int | None) -> Span:
    """The range of what is left once a slice with plain bounds is deleted."""
    cut = slice(start, stop)
    return over(span, lambda count: count - taken(cut, count), _breaks(start, stop), 1)


def taken(cut: slice, count: int) -> int:
    """How many items ``cut`` takes from ``count``, as Python's own clamp
    (``slice.indices``) cuts it, counted by arithmetic so a bound past ``sys.maxsize`` is
    one more int."""
    start, stop, step = cut.indices(count)
    if step > 0:
        return max(0, (stop - start + step - 1) // step)
    return max(0, (start - stop - step - 1) // -step)


def over(span: Span, count: Callable[[int], int], breaks: tuple[int, ...], step: int) -> Span:
    """The fewest and the most ``count`` gives for any length in ``span``.

    Between its ``breaks`` ``count`` is monotone, as a clamp and a count of every ``step``-th
    item are, so its ends on the range are found at the range's own ends and at each break
    inside it; past the last break it grows without a most, one item every ``step``, or stays.
    """
    least, top = span[0] or 0, span[1]
    far = max((least, *breaks)) + 2
    last = far if top is None else top
    points = {least, last, *(at for at in breaks if least <= at <= last)}
    counts = [count(at) for at in points]
    endless = top is None and count(far + step) > count(far)
    return (min(counts), None if endless else max(counts))


def proves(span: Span, op: str, number: int) -> bool | None:
    """What the range says of ``length op number``: True or False when every length in it
    answers so, None when lengths in it answer both ways."""
    fewest, most = span
    if op in ("==", "!="):
        if fewest == number and most == number:
            return op == "=="
        if (most is not None and most < number) or (fewest is not None and fewest > number):
            return op == "!="
        return None
    if op in ("<", "<="):
        flipped = proves(span, ">=" if op == "<" else ">", number)
        return None if flipped is None else not flipped
    floor = number if op == ">" else number - 1
    if fewest is not None and fewest > floor:
        return True
    if most is not None and most <= floor:
        return False
    return None


def narrowed(span: Span, op: str, number: int, taken: bool) -> Span:
    """The range once a fork on ``length op number`` took ``taken``: only the lengths in it that
    answer so. A fork the range could not hold leaves only what the fork says."""
    fewest, most = _answered(op, number, taken, span)
    if fewest is not None and most is not None and fewest > most:
        return _answered(op, number, taken, UNKNOWN)
    return (fewest, most)


class Measured(Protocol):
    """A value that keeps a length range: a tracked list or string. It refuses a set, as the
    plain value does, so the range is written straight into its ``__dict__``."""

    sink: BranchSink
    span: Span


def measured(
    value: Measured,
    expression: list[Expression],
    taken: bool,
    name: str = "__bool__",
    *,
    raising: bool = False,
) -> bool:
    """Record a check on a value's length, ``[op, length, n]`` with a plain ``n``: a fact where
    the value's range proves the side Python took, else a fork, which narrows the range. Answer
    that side."""
    op, _, number = expression
    assert isinstance(op, str) and type(number) is int
    span = value.span
    if proves(span, op, number) is taken:
        return held(value.sink, expression, taken, name, raising=raising)
    value.__dict__["span"] = narrowed(span, op, number, taken)
    return forked(value.sink, expression, taken, name, raising=raising)


def decided(sink: BranchSink, span: Span, expression: list[Expression], taken: bool) -> bool:
    """Whether the range proves the side Python took on ``[op, length, n]``, recording the fact
    where it does; nothing is recorded where it does not, and the caller's check stays a fork."""
    op, _, number = expression
    assert isinstance(op, str) and type(number) is int
    if proves(span, op, number) is not taken:
        return False
    held(sink, expression, taken)
    return True


def _answered(op: str, number: int, taken: bool, span: Span) -> Span:
    fewest, most = span
    if op in ("<", "<="):
        return _answered(">=" if op == "<" else ">", number, not taken, span)
    if op in ("==", "!="):
        if (op == "==") is taken:
            return (_most_of(fewest, number), _least_of(most, number))
        fewest = number + 1 if fewest == number else fewest
        return (fewest, number - 1 if most == number else most)
    floor = number if op == ">" else number - 1
    if taken:
        return (_most_of(fewest, floor + 1), most)
    return (fewest, _least_of(most, floor))


def _breaks(start: int | None, stop: int | None) -> tuple[int, ...]:
    """Where a slice's count may change its slope, as the length grows: at each bound's size,
    where the two clamped bounds cross, at the sum of the sizes, and one past each, which a
    step back from the end reads."""
    sizes = [abs(bound) for bound in (start, stop) if bound is not None]
    return tuple(at for size in (*sizes, sum(sizes)) for at in (size, size + 1))


def _sum(left: int | None, right: int | None) -> int | None:
    return None if left is None or right is None else left + right


def _times(bound: int | None, times: int) -> int | None:
    if times == 0:
        return 0
    return None if bound is None else bound * times


def _most_of(bound: int | None, other: int) -> int:
    return other if bound is None else max(bound, other)


def _least_of(bound: int | None, other: int) -> int:
    return other if bound is None else min(bound, other)
