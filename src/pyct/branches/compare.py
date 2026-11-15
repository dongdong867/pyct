"""Where a run's path left the plan it was solved for, and whether two forks' expressions are
the same."""

import struct

from pyct.core.foundation.branch import Branch, Expression


def compare(planned: tuple[Branch, ...], actual: tuple[Branch, ...]) -> int | None:
    """The first position where ``actual`` stops following ``planned``.

    A fork is followed when it happens at the same site and takes the same
    side. A run that goes on forking past the plan still followed it, so
    only the planned positions are read.
    """
    for position, wanted in enumerate(planned):
        if position >= len(actual) or not _follows(wanted, actual[position]):
            return position
    return None


def _follows(wanted: Branch, took: Branch) -> bool:
    """Whether one fork of a run is the fork the plan asked for at that position."""
    return took.site == wanted.site and took.taken == wanted.taken


class Parts:
    """How many more parts of expressions the comparisons that share it may compare."""

    def __init__(self, left: int) -> None:
        self.left = left


def same_expression(one: Expression, other: Expression, parts: Parts) -> bool | None:
    """Whether two expressions are the same: equal in structure, each literal of the same type,
    each float with the same bits, so ``1``, ``1.0`` and ``True`` differ and so do ``0.0`` and
    ``-0.0``. None when ``parts`` runs out first.

    Each pair of parts taken up spends one of ``parts``. A pair of lists is
    taken up once, however often the two expressions share it, and the walk
    keeps its own stack, so a deep chain needs no recursion.
    """
    taken: set[tuple[int, int]] = set()
    pending: list[tuple[Expression, Expression]] = [(one, other)]
    while pending:
        if parts.left <= 0:
            return None
        parts.left -= 1
        first, second = pending.pop()
        if first is second:
            continue
        if type(first) is not type(second):
            return False
        if isinstance(first, list) and isinstance(second, list):
            if len(first) != len(second):
                return False
            if (id(first), id(second)) not in taken:
                taken.add((id(first), id(second)))
                pending.extend(zip(first, second, strict=True))
        elif not _same_literal(first, second):
            return False
    return True


def _same_literal(one: Expression, other: Expression) -> bool:
    """Whether two literals of one type are the same, a float by its bits."""
    if isinstance(one, float) and isinstance(other, float):
        return struct.pack("<d", one) == struct.pack("<d", other)
    return one == other
