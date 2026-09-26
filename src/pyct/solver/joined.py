"""Two pieces of one string joined back up, written as the one piece they make.

For a string t and bounds a <= b <= c, none of them negative, Python's
``t[a:b] + t[b:c]`` is ``t[a:c]`` whatever t's length, since each slice
clamps to the same end; and ``t[i]``, past the fork that says t is long
enough, is ``t[i:i+1]``. A join that makes the whole string is t itself.
So a loop that takes a string apart and puts it back together, as
``s = s[:i] + s[i] + s[i+1:]`` does, hands the solver the string it started
from, where written as it stands cvc5 ran eighteen passes of it past its
time limit. The condition means what it meant; only the way it is written
changes.
"""

from dataclasses import replace

from pyct.core.branch import Branch, Expression
from pyct.solver.dag import Node, distinct

# a piece of a string: the string, and where the piece starts and stops, None for an end
type _Span = tuple[Expression, int | None, int | None]


def joined(prefix: tuple[Branch, ...]) -> tuple[Branch, ...]:
    """The path with every join of two adjacent pieces of one string written as one piece.

    Each distinct part is rewritten once, so a part held in many places is
    still one part, and one that nothing joins is left as it is.
    """
    order, _ = distinct(prefix)
    written: dict[int, Expression] = {}
    for node in order:
        written[id(node)] = _rejoined(node, written)
    return tuple(
        replace(fork, expression=written[id(fork.expression)])
        if isinstance(fork.expression, list)
        else fork
        for fork in prefix
    )


def _rejoined(node: Node, written: dict[int, Expression]) -> Expression:
    """A part with its operands rewritten, and itself one piece if it joins two."""
    head, *operands = node
    parts = [written[id(part)] if isinstance(part, list) else part for part in operands]
    if head == "+" and len(parts) == 2 and (whole := _join(parts[0], parts[1])) is not None:
        return whole
    if all(part is operand for part, operand in zip(parts, operands, strict=True)):
        return node
    return [head, *parts]


def _join(left: Expression, right: Expression) -> Expression | None:
    """The one piece two pieces of one string make, side by side, or None when they do not."""
    first, second = _span(left), _span(right)
    if first is None or second is None or not _same(first[0], second[0]):
        return None
    term, start, middle = first
    _, after, stop = second
    if middle is None or middle != (after or 0) or (start or 0) > middle:
        return None
    if stop is not None and stop < middle:
        return None
    return term if not start and stop is None else ["[:]", term, start, stop]


def _span(part: Expression) -> _Span | None:
    """A piece of a string with no negative bound, as its string and its bounds, or None."""
    if not isinstance(part, list) or len(part) < 3 or not all(map(_ahead, part[2:])):
        return None
    if part[0] == "[]" and len(part) == 3 and isinstance(part[2], int):
        return part[1], part[2], part[2] + 1
    if part[0] == "[:]" and len(part) == 4:
        start, stop = part[2], part[3]
        if (start is None or isinstance(start, int)) and (stop is None or isinstance(stop, int)):
            return part[1], start, stop
    return None


def _ahead(bound: Expression) -> bool:
    """Whether a bound counts from the start: a plain int of zero or more, or a missing one."""
    return bound is None or (isinstance(bound, int) and not isinstance(bound, bool) and bound >= 0)


def _same(one: Expression, other: Expression) -> bool:
    """Whether two terms are one string: the same list, or the same name or literal."""
    return one is other or (not isinstance(one, list) and one == other)
