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
from pyct.solver.dag import IsLeaf, Node, distinct

# a piece of a string: the string, and where the piece starts and stops, None for an end
type _Span = tuple[Expression, int | None, int | None]


def joined(prefix: tuple[Branch, ...], is_leaf: IsLeaf) -> tuple[Branch, ...]:
    """The path with every join of two adjacent pieces of one string written as one piece.

    Each distinct part is rewritten once, so a part held in many places is
    still one part, and one that nothing joins is left as it is. A leaf of
    the seed is a value, not a piece, even when it is an item of a list.
    """
    order, _ = distinct(prefix, is_leaf)
    written: dict[int, Expression] = {}
    for node in order:
        written[id(node)] = _rejoined(node, written, is_leaf)
    return tuple(
        replace(fork, expression=written.get(id(fork.expression), fork.expression))
        if isinstance(fork.expression, list)
        else fork
        for fork in prefix
    )


def _rejoined(node: Node, written: dict[int, Expression], is_leaf: IsLeaf) -> Expression:
    """A part with its operands rewritten, and itself one piece if it joins two."""
    head, *operands = node
    parts = [written.get(id(part), part) if isinstance(part, list) else part for part in operands]
    pieces = len(parts) == 2 and not any(is_leaf(part) for part in parts)
    if head == "+" and pieces and (whole := _join(parts[0], parts[1])) is not None:
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
    match part:
        case ["[]", term, int() as index] if _ahead(index):
            return term, index, index + 1
        case ["[:]", term, None | int() as start, None | int() as stop] if _ahead(start, stop):
            return term, start, stop
    return None


def _ahead(*bounds: Expression) -> bool:
    """Whether each bound counts from the start: a plain int of zero or more, or a missing one."""
    return all(
        bound is None or (isinstance(bound, int) and not isinstance(bound, bool) and bound >= 0)
        for bound in bounds
    )


def _same(one: Expression, other: Expression) -> bool:
    """Whether two terms are one string: the same list, or the same name or literal."""
    return one is other or (not isinstance(one, list) and one == other)
