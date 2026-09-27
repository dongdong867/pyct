"""Graph walks the flow of a function is read with: orders, dominators, and lines as bits.

Each walk takes the analysis's ``Pace``, which looks at the run's clock every
so many steps and ends the analysis with ``OutOfTimeError`` once its stop has
come. The stop is the analysis's own: it is raised only where a walk steps
or asks ahead, never by a signal, so nothing else the process does meets it.
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

# how many steps pass between two looks at the clock: a look costs a clock read, and a step
# is a node, a line or an input, microseconds at most
_EVERY = 256


def strictly_after(parts: set[int], bits: tuple[list[int], list[int], list[int]]) -> int:
    """The lines, as bits, in parts after ``parts`` that cannot reach back into them."""
    held, later, earlier = bits
    after = back = same = 0
    for each in parts:
        after |= later[each]
        back |= earlier[each]
        same |= held[each]
    return after & ~back & ~same


def postorder(successors: list[list[int]], *roots: int, pace: Pace | None = None) -> list[int]:
    """The nodes reachable from ``roots``, each after every node it leads to first."""
    order: list[int] = []
    seen = set(roots)
    stack: list[tuple[int, Iterator[int]]] = [(root, iter(successors[root])) for root in roots]
    while stack:
        if pace is not None:
            pace.step()
        node, pending = stack[-1]
        following = next((each for each in pending if each not in seen), None)
        if following is None:
            stack.pop()
            order.append(node)
            continue
        seen.add(following)
        stack.append((following, iter(successors[following])))
    return order


class OutOfTimeError(BaseException):
    """The run's stop came while the cause analysis was running.

    A BaseException, not an Exception, so no ``except Exception`` on the way
    can swallow it.
    """


def never(_ahead: float = 0.0) -> bool:
    """A stop that never comes: the check for a run with no deadline."""
    return False


@dataclass
class Pace:
    """The analysis's stop: every ``_EVERY`` steps it asks ``late`` whether the stop has come,
    and raises OutOfTimeError when it has. ``late(ahead)`` says whether it comes within
    ``ahead`` seconds, so work no step can break into asks first (``afford``).

    Each walk whose work grows with the function, the lines or the inputs
    steps it once per node, line, input or climb, so no walk runs long past
    the stop. Work no step can break into asks ``afford`` first.
    """

    late: Callable[[float], bool] = never
    steps: int = 0

    def step(self) -> None:
        self.steps += 1
        if self.steps % _EVERY == 0 and self.late(0.0):
            raise OutOfTimeError

    def each[T](self, items: Iterable[T]) -> Iterator[T]:
        """``items``, one step each."""
        for item in items:
            self.step()
            yield item

    def afford(self, seconds: float) -> None:
        """Raise OutOfTimeError now when work that cannot step, and may take ``seconds``,
        would run past the stop."""
        if self.late(seconds):
            raise OutOfTimeError


def dominators(
    successors: list[list[int]], root: int, number: dict[int, int], pace: Pace
) -> dict[int, int]:
    """Each reachable node's immediate dominator, the root its own (Cooper, Harvey and Kennedy).

    ``number`` is each reachable node's place in the postorder from ``root``.
    """
    order = sorted(number, key=number.__getitem__)
    predecessors: dict[int, list[int]] = {node: [] for node in order}
    for node in order:
        for following in successors[node]:
            predecessors[following].append(node)
    idom = {root: root}
    changed = True
    while changed:
        changed = False
        for node in reversed(order[:-1]):
            pace.step()
            known = [each for each in predecessors[node] if each in idom]
            meet = functools.reduce(lambda a, b: intersect(a, b, idom, number, pace), known)
            if idom.get(node) != meet:
                idom[node] = meet
                changed = True
    return idom


def intersect(a: int, b: int, idom: dict[int, int], number: dict[int, int], pace: Pace) -> int:
    """The nearest node that dominates both ``a`` and ``b``, one step a climb."""
    while a != b:
        while number[a] < number[b]:
            pace.step()
            a = idom[a]
        while number[b] < number[a]:
            pace.step()
            b = idom[b]
    return a
