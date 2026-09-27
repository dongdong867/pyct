"""Graph walks the flow of a function is read with: orders, dominators, and lines as bits."""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterator


def strictly_after(parts: set[int], bits: tuple[list[int], list[int], list[int]]) -> int:
    """The lines, as bits, in parts after ``parts`` that cannot reach back into them."""
    held, later, earlier = bits
    after = back = same = 0
    for each in parts:
        after |= later[each]
        back |= earlier[each]
        same |= held[each]
    return after & ~back & ~same


def postorder(successors: list[list[int]], *roots: int) -> list[int]:
    """The nodes reachable from ``roots``, each after every node it leads to first."""
    order: list[int] = []
    seen = set(roots)
    stack: list[tuple[int, Iterator[int]]] = [(root, iter(successors[root])) for root in roots]
    while stack:
        node, pending = stack[-1]
        following = next((each for each in pending if each not in seen), None)
        if following is None:
            stack.pop()
            order.append(node)
            continue
        seen.add(following)
        stack.append((following, iter(successors[following])))
    return order


class OutOfTimeError(Exception):
    """The run's stop came while a step whose cost grows with the function was running."""


def never() -> bool:
    """A stop that never comes: the check for a run with no deadline."""
    return False


def dominators(
    successors: list[list[int]], root: int, number: dict[int, int], late: Callable[[], bool] = never
) -> dict[int, int]:
    """Each reachable node's immediate dominator, the root its own (Cooper, Harvey and Kennedy).

    ``number`` is each reachable node's place in the postorder from ``root``.
    ``late`` is asked before each pass over the nodes, which is how the
    work grows with the function.
    """
    order = sorted(number, key=number.__getitem__)
    predecessors: dict[int, list[int]] = {node: [] for node in order}
    for node in order:
        for following in successors[node]:
            predecessors[following].append(node)
    idom = {root: root}
    changed = True
    while changed:
        if late():
            raise OutOfTimeError
        changed = False
        for node in reversed(order[:-1]):
            known = [each for each in predecessors[node] if each in idom]
            meet = functools.reduce(lambda a, b: intersect(a, b, idom, number), known)
            if idom.get(node) != meet:
                idom[node] = meet
                changed = True
    return idom


def intersect(a: int, b: int, idom: dict[int, int], number: dict[int, int]) -> int:
    """The nearest node that dominates both ``a`` and ``b``."""
    while a != b:
        while number[a] < number[b]:
            a = idom[a]
        while number[b] < number[a]:
            b = idom[b]
    return a
