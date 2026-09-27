"""The positions a tracked str is read at: an index, a slice's bounds and step, a search's start
and end.

A position pyct follows is a plain int or a plain bool, read as the int it
is, or a tracked int, read by its expression, so the solver may move it. A
tracked bool, the answer of a compare, is not one. None stands where Python
takes None. Any other value is a form pyct does not encode.
"""

from __future__ import annotations

from collections.abc import Sequence

from pyct.core.branch import Expression
from pyct.core.ints import ConcolicInt
from pyct.core.str_cases import Tracked
from pyct.core.str_operands import position
from pyct.core.values import forked, own

# the steps a followed slice takes: one character forward, or one back
_STEPS = (1, -1)


def placed(value: object) -> Expression | None:
    """A position as the solver reads it: a plain int or bool as the int, a tracked int by its
    expression. Any other value is None."""
    if isinstance(value, ConcolicInt):
        return value.expression
    return position(value)


def placed_or_missing(values: Sequence[object]) -> list[Expression] | None:
    """Each value as `placed` reads it, and None where Python takes None; None when any value
    is neither."""
    forms = [None if value is None else placed(value) for value in values]
    if any(form is None and value is not None for form, value in zip(forms, values, strict=True)):
        return None
    return forms


def slice_bounds(key: object) -> list[Expression] | None:
    """The start and the stop of a slice pyct encodes, a missing bound as None, then its step.

    A step of None is no step and is left out. A plain step of 1 or -1 is
    written as a third bound; any other step, a tracked one included, and
    any other key are None.
    """
    if not isinstance(key, slice):
        return None
    bounds = placed_or_missing([key.start, key.stop])
    if key.step is None or bounds is None:
        return bounds
    step = position(key.step)
    return [*bounds, step] if step in _STEPS else None


def search_positions(args: Sequence[object]) -> list[Expression] | None:
    """The start, or the start and the end, a search is given, a None kept as None; None for
    more than two or for a position pyct does not encode."""
    return placed_or_missing(args) if len(args) <= 2 else None


def long_enough(s: Tracked, key: int, index: Expression) -> None:
    """The forks an index takes on its way to a raise: whether s is long enough for it.

    A plain index records one fork: `[">", ["len", s], i]` for an index of
    zero or more, and `[">=", ["len", s], -i]` for a negative one, which
    counts back from the end. A tracked index may be either, so it records
    Python's `-len(s) <= n < len(s)` as two forks, `[">", ["len", s], n]`
    and then, when that holds, `[">=", ["len", s], ["-", n]]`. Each goes in
    before str's own index may raise IndexError, as a search's fork does for
    ValueError. str's own length, and the index's own int, so the compare
    records nothing of its own.
    """
    length = own(str.__len__, s)
    at = int.__index__(key)
    measured: Expression = ["len", s.expression]
    if not isinstance(key, ConcolicInt):
        if at >= 0:
            forked(s.sink, [">", measured, at], length > at)
        else:
            forked(s.sink, [">=", measured, -at], length >= -at)
    elif forked(s.sink, [">", measured, index], length > at):
        forked(s.sink, [">=", measured, ["-", index]], length >= -at)
