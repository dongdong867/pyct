"""How a change to a tracked list is written: as the Python expression that builds the result.

Each builder takes the forms it joins and hands back the new form, as
follow-lists-and-dicts-as-they-change's table writes it: `items.append(x)` is `items + [x]`,
`insert(i, x)` is `items[:i] + [x] + items[i:]`, and so on. A list display is the head
``"[,]"`` with its items in order.

A value goes into a display as the expression that stands for it: a tracked value's own, a
plain int, float, bool or None as itself, a plain str as ``repr`` writes it, and a list as its
own form or a display of its items. Any other value, a dict or an object say, has no expression
here, and the change that stores it is a downgrade.
"""

from __future__ import annotations

from collections.abc import Iterable
from enum import Enum

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Expression
from pyct.core.ints import ConcolicInt
from pyct.core.list_state import ListState
from pyct.core.strs import ConcolicStr

# how deep a plain list inside a stored value may nest before it is not written: a display is
# written by Python's own recursion, well within its limit
_DEPTH = 64

# the plain values a display writes as themselves: JSON reads each back
_AS_THEMSELVES: tuple[type, ...] = (int, float, bool, type(None))


class _Unwritten(Enum):
    """What ``written`` answers for a value no expression here holds."""

    VALUE = "a value no expression holds"


UNWRITTEN = _Unwritten.VALUE


def written(value: object, depth: int = 0) -> Expression | _Unwritten:
    """The expression that stands for a value stored in a tracked list, or ``UNWRITTEN``."""
    if isinstance(value, ConcolicInt | ConcolicStr | ConcolicBool):
        return value.expression
    if type(value) in _AS_THEMSELVES:
        return value  # type: ignore[return-value]
    if type(value) is str:
        return str.__repr__(value)
    if isinstance(value, ListState) and value.expression is not None:
        return value.expression
    if isinstance(value, list) and (type(value) is list or isinstance(value, ListState)):
        return displayed(list.copy(value), depth + 1)
    return UNWRITTEN


def displayed(values: Iterable[object], depth: int = 0) -> Expression | _Unwritten:
    """A list display of the values, ``["[,]", ...]``, or ``UNWRITTEN`` when one is not written."""
    if depth > _DEPTH:
        return UNWRITTEN
    items: list[Expression] = ["[,]"]
    for value in values:
        form = written(value, depth)
        if form is UNWRITTEN:
            return UNWRITTEN
        items.append(form)
    return items


def sliced(form: Expression, start: Expression, stop: Expression) -> Expression:
    """``form[start:stop]``, a missing bound written None."""
    return ["[:]", form, start, stop]


def joined(*forms: Expression) -> Expression:
    """The forms added up left to right, as Python reads ``a + b + c``."""
    whole = forms[0]
    for form in forms[1:]:
        whole = ["+", whole, form]
    return whole


def dropped(form: Expression, index: Expression) -> Expression:
    """The form without the item at ``index``: ``items[:i] + items[i:][1:]``."""
    return joined(sliced(form, None, index), sliced(sliced(form, index, None), 1, None))


def put(form: Expression, index: Expression, item: Expression) -> Expression:
    """The form with ``item`` in place of the one at ``index``: ``items[:i] + [x] + items[i:][1:]``."""
    after = sliced(sliced(form, index, None), 1, None)
    return joined(sliced(form, None, index), ["[,]", item], after)


def placed(form: Expression, index: Expression, item: Expression) -> Expression:
    """The form with ``item`` inserted before ``index``: ``items[:i] + [x] + items[i:]``."""
    return joined(sliced(form, None, index), ["[,]", item], sliced(form, index, None))


def spliced(form: Expression, bounds: tuple[Expression, Expression], middle: Expression | None) -> Expression:
    """The form with ``[a:b]`` replaced by ``middle``, or deleted when it is None.

    ``items[:a] + ys + items[a:][len(items[a:b]):]``, a missing ``a`` written as 0: the part
    after the cut starts where ``[a:b]`` ends whatever the two bounds are, as Python cuts.
    """
    start, stop = bounds
    start = 0 if start is None else start
    after = sliced(sliced(form, start, None), ["len", sliced(form, start, stop)], None)
    before = sliced(form, None, start)
    return joined(before, after) if middle is None else joined(before, middle, after)
