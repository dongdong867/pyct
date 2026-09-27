"""A tracked value turned into text alone: `str(x)`, `format(x)` and `f"{x}"`.

Python hands the str a value's `__str__` gives back on whole through
`str(x)`, `print`, `"%s" % x` and `map(str, ...)`, and through `format(x)`,
`f"{x}"` and `"{}".format(x)`, which reach it by `__format__` with no spec.
So a tracked int's or bool's text is a tracked str, `["str", x]`, and a
tracked str's is the value itself, and the condition survives each. Text
joined around the value, as in `f"n={x}"`, is Python's own plain str, since
Python joins the pieces without calling any method of the tracked one.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pyct.core import numbers
from pyct.core.branch import Expression
from pyct.core.values import First, own


def _its_expression(value: numbers.Number) -> Expression:
    return value.expression


def text(
    written: Callable[[Any], str], read: Callable[[Any], Expression] = _its_expression
) -> Callable[[Any], Any]:
    """A tracked int's or bool's `__str__`: the text Python writes, carrying `["str", x]`.

    ``written`` writes the text of the plain value, and a raise out of it,
    past Python's digit limit say, is the target's. ``read`` is the node the
    text reads, the value's expression unless its type says otherwise.
    """

    def compute(self: numbers.Number) -> Any:
        return numbers.tracked(own(written, self), ["str", read(self)], self.sink)

    return compute


def alone(written: Callable[[Any], object]) -> First:
    """What a tracked value's `__format__` answers first: with no format spec, its own text.

    Python formats a value with no spec, `format(x)` or `f"{x}"`, as the
    text `str(x)` writes, so it is ``written``'s answer, as tracked as that
    is. A spec, or a tracked one, goes on to the base type's own format.
    """

    def first(_name: str, value: object, spec: object) -> object:
        return written(value) if type(spec) is str and not spec else NotImplemented

    return first
