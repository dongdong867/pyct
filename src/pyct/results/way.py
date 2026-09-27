"""A line's way: the conditions every run of its function passes to reach the line.

Read from the compiled code, not the source, so an early ``return`` counts:
the lines after ``if x: return`` need the test's false side, which the
nesting of the source does not show (decision
why-missed-first-untaken-condition-from-control-flow). A function's flow
is its basic blocks joined by their jumps. A raise into an ``except`` block,
a ``finally`` or the cleanup Python compiles for a ``with``, a
comprehension or an ``await`` is one node, reached from every block the
handler's range covers, so a guard around a ``try`` guards its handler too.
A condition's two sides are nodes of their own between its block and the
next, so "every run passes this side" is "this node dominates the line".
"""

from __future__ import annotations

import functools
import types
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from pyct.results.blocks import Op, Step, StepKind, blocks_of_code, exits, handler_ranges

# CPython's flag on a function's code; a module and a class body run without it
_OPTIMIZED = 0x1


@dataclass(frozen=True)
class Place:
    """A step as a walk meets it: the side's node, and the node the side leaves."""

    step: Step
    node: int
    source: int


# a fork as the flow reads it: its line and column, the side it took, and whether it is an
# operation's before a raise
type Fork = tuple[int, int, bool, bool]


def owners(module: types.CodeType) -> dict[int, types.CodeType | None]:
    """Each line of a module, and the code that runs it: None when the module's import does.

    The import runs the module's own code and each class body in it, so a
    ``def`` line, a decorator, and a class's attributes are the import's. A
    line two functions hold, such as an inner ``def`` line, is the outer
    one's: it runs when the outer function does.
    """
    held: dict[int, types.CodeType | None] = {}
    at_import, functions = _split_by_when(module)
    for code in at_import:
        held.update(dict.fromkeys(_lines(code)))
    for code in functions:
        for line in _lines(code):
            held.setdefault(line, code)
    return held


def _split_by_when(module: types.CodeType) -> tuple[list[types.CodeType], list[types.CodeType]]:
    """The codes the import runs, and every other code, outermost first."""
    at_import: list[types.CodeType] = []
    functions: list[types.CodeType] = []
    stack: list[tuple[types.CodeType, bool]] = [(module, True)]
    while stack:
        code, import_runs_it = stack.pop()
        (at_import if import_runs_it else functions).append(code)
        inner = [c for c in code.co_consts if isinstance(c, types.CodeType)]
        stack.extend((c, import_runs_it and not c.co_flags & _OPTIMIZED) for c in reversed(inner))
    return at_import, functions


def _lines(code: types.CodeType) -> set[int]:
    return {line for _, _, line in code.co_lines() if line}


class Flow:
    """One function's blocks, sides and raises, with who dominates whom.

    ``raising`` holds the positions, ``(line, col)``, where a run recorded
    a fork before an operation that may raise; the instruction there is a
    condition whose true side goes on to the next instruction.
    """

    def __init__(self, code: types.CodeType, raising: frozenset[tuple[int, int]]) -> None:
        graph = _Graph.of(code, raising)
        self._graph = graph
        self._order = {n: at for at, n in enumerate(_postorder(graph.successors, graph.entry))}
        self._idom = _dominators(graph.successors, graph.entry, self._order)
        self._normal = frozenset(_postorder(graph.normal, graph.entry))

    def way(self, line: int) -> tuple[Step, ...]:
        """The steps every run takes to reach ``line``, in the order it takes them."""
        return tuple(place.step for place in self.places(line))

    def places(self, line: int) -> tuple[Place, ...]:
        """The way's steps as places, in the order a run meets them."""
        return tuple(self._place(node) for node in self.chain(line) if node in self._graph.steps)

    def chain(self, line: int) -> list[int]:
        """Every node every run passes on its way to ``line``, the function's entry first."""
        meet = self._meet_of(self._holders(line))
        return [] if meet is None else list(reversed(self._up(meet)))

    def reaching(self, line: int) -> tuple[Place, ...]:
        """Each condition's side from which ``line`` can still be reached, in test order."""
        toward = self._toward(line)
        sides = [
            node
            for node, step in self._graph.steps.items()
            if step.kind is StepKind.CONDITION and node in toward and node in self._order
        ]
        return tuple(self._place(node) for node in sorted(sides, key=self._tested_before))

    def marked(self, lines: Iterable[int], forks: Iterable[Fork]) -> frozenset[int]:
        """The nodes a run passed, as far as covered lines and recorded forks prove it.

        A line proves the nodes that dominate every block that holds it; a fork
        proves the side it took, or, for an operation that raised, its block.
        """
        found: set[int] = set()
        for line in set(lines):
            found.update(self._proved(self._holders(line)))
        for fork in set(forks):
            found.update(self._proved(self._graph.forked(fork)))
        return frozenset(found)

    @functools.cached_property
    def _by_lines(self) -> frozenset[int]:
        """The nodes some line could prove a run passed, were it covered."""
        return self.marked(self._graph.lines(), ())

    @functools.cached_property
    def _by_forks(self) -> dict[int, set[tuple[int, int, bool]]]:
        """Each node, and the tests whose forks could prove a run passed it."""
        proving: dict[int, set[tuple[int, int, bool]]] = {}
        sides = self._graph.steps.items()
        for node, step in [(n, s) for n, s in sides if s.kind is StepKind.CONDITION]:
            # a side no run can reach proves nothing
            for each in self._up(node) if node in self._idom else ():
                proving.setdefault(each, set()).add((step.line, step.col, step.raising))
        return proving

    def knowable(self, place: Place) -> bool:
        """Whether a run could show it took this side, when the side's own test forks nowhere.

        It can when a line only this side leads to is covered, or another test
        only this side leads to records a fork. The sides of a ternary, which
        join again at once, show nothing.
        """
        step = place.step
        own = (step.line, step.col, step.raising)
        others = self._by_forks.get(place.node, set()) - {own}
        return place.node in self._by_lines or bool(others)

    def only_in_handlers(self, line: int) -> bool:
        """Whether only a raise reaches ``line``: no block that holds it runs without one."""
        holders = self._graph.blocks_of(line)
        return bool(holders) and not any(block in self._normal for block in holders)

    def last_yield(self, nodes: frozenset[int]) -> int | None:
        """The line of the yield in the latest of ``nodes`` that holds one, or None."""
        held = [node for node in nodes if node in self._graph.yields and node in self._order]
        if not held:
            return None
        return self._graph.yields[min(held, key=self._order.__getitem__)]

    def raises_toward(self, line: int) -> frozenset[int]:
        """The raise nodes entered from a block ``line`` can still be reached from."""
        toward = self._toward(line)
        before = self._graph.predecessors()
        return frozenset(r for r in self._graph.raises if toward.intersection(before[r]))

    def toward(self, line: int) -> frozenset[int]:
        """The nodes from which ``line`` can still be reached."""
        return self._toward(line)

    def _place(self, node: int) -> Place:
        return Place(self._graph.steps[node], node, self._idom[node])

    def _holders(self, line: int) -> list[int]:
        return [block for block in self._graph.blocks_of(line) if block in self._idom]

    def _meet_of(self, nodes: list[int]) -> int | None:
        reachable = [node for node in nodes if node in self._idom]
        if not reachable:
            return None
        return functools.reduce(lambda a, b: _intersect(a, b, self._idom, self._order), reachable)

    def _proved(self, nodes: list[int]) -> list[int]:
        meet = self._meet_of(nodes)
        return [] if meet is None else self._up(meet)

    def _up(self, node: int) -> list[int]:
        """``node`` and every node that dominates it, nearest first."""
        found = [node]
        while node != self._graph.entry:
            node = self._idom[node]
            found.append(node)
        return found

    def _toward(self, line: int) -> frozenset[int]:
        return frozenset(_postorder(self._graph.predecessors(), *self._holders(line)))

    def _tested_before(self, node: int) -> tuple[int, int]:
        """Test order: the node a side leaves, earliest first, then the side's own number."""
        return (-self._order[self._idom[node]], node)


@dataclass(frozen=True)
class _Graph:
    """The blocks, sides and raises as numbered nodes.

    Nodes below ``len(lines)`` are blocks; the ones above are sides and
    raises, each with its step. ``normal`` is the flow with the raises left out.
    """

    successors: list[list[int]]
    normal: list[list[int]]
    steps: dict[int, Step]
    held: dict[int, frozenset[int]]
    raises: tuple[int, ...]
    entry: int
    yields: dict[int, int]

    @classmethod
    def of(cls, code: types.CodeType, raising: frozenset[tuple[int, int]]) -> _Graph:
        blocks, splits = blocks_of_code(code, raising)
        builder = _Builder(blocks)
        for index, block in enumerate(blocks):
            for target, step in exits(block, blocks, index, splits):
                builder.join(index, builder.block_at(target), step)
        normal = [list(each) for each in builder.successors]
        for start, covered in handler_ranges(code, blocks):
            builder.raise_into(start, covered)
        normal += [[] for _ in range(len(builder.successors) - len(normal))]
        yields = {
            index: op.line
            for index, block in enumerate(blocks)
            for op in block
            if op.name == "YIELD_VALUE" and op.line
        }
        steps = builder.steps
        return cls(builder.successors, normal, steps, builder.held(), builder.raises, 0, yields)

    def blocks_of(self, line: int) -> list[int]:
        return [block for block, lines in self.held.items() if line in lines]

    def lines(self) -> set[int]:
        return {line for lines in self.held.values() for line in lines}

    def predecessors(self) -> list[list[int]]:
        before: list[list[int]] = [[] for _ in self.successors]
        for node, following in enumerate(self.successors):
            for each in following:
                before[each].append(node)
        return before

    def forked(self, fork: Fork) -> list[int]:
        """The nodes a fork proves: the side it took, or the block of an operation that raised."""
        return self._proved_by.get(fork, [])

    @functools.cached_property
    def _proved_by(self) -> dict[Fork, list[int]]:
        """Each fork the code can record, and the nodes it proves. Built once, read per fork."""
        proved: dict[Fork, list[int]] = {}
        for node, step in self.steps.items():
            if step.kind is not StepKind.CONDITION:
                continue
            proved.setdefault((step.line, step.col, step.side, step.raising), []).append(node)
            if step.raising:
                source = next(n for n, following in enumerate(self.successors) if node in following)
                proved.setdefault((step.line, step.col, False, True), []).append(source)
        return proved


class _Builder:
    """Numbers the nodes as the graph is built."""

    def __init__(self, blocks: list[list[Op]]) -> None:
        self.blocks = blocks
        self.starts = {block[0].offset: index for index, block in enumerate(blocks)}
        self.successors: list[list[int]] = [[] for _ in blocks]
        self.steps: dict[int, Step] = {}
        self.raises: tuple[int, ...] = ()

    def node(self) -> int:
        self.successors.append([])
        return len(self.successors) - 1

    def block_at(self, offset: int) -> int:
        return self.starts[offset]

    def join(self, source: int, target: int, step: Step | None) -> None:
        """Join two nodes, through a side node of its own when the way passes a step."""
        if step is None:
            self.successors[source].append(target)
            return
        side = self.node()
        self.steps[side] = step
        self.successors[source].append(side)
        self.successors[side].append(target)

    def raise_into(self, start: int, covered: Iterable[int]) -> None:
        """One raise node into the handler at ``start``, from every block its range covers."""
        target = self.block_at(start)
        first = next((op.line for op in self.blocks[target] if op.line), None)
        into = self.node()
        self.steps[into] = Step(StepKind.HANDLER, first or 0, 0, True)
        self.raises = (*self.raises, into)
        self.successors[into].append(target)
        for offset in covered:
            self.successors[self.block_at(offset)].append(into)

    def held(self) -> dict[int, frozenset[int]]:
        return {
            index: frozenset(op.line for op in block if op.line)
            for index, block in enumerate(self.blocks)
        }


def _postorder(successors: list[list[int]], *roots: int) -> list[int]:
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


def _dominators(successors: list[list[int]], root: int, number: dict[int, int]) -> dict[int, int]:
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
            known = [each for each in predecessors[node] if each in idom]
            meet = functools.reduce(lambda a, b: _intersect(a, b, idom, number), known)
            if idom.get(node) != meet:
                idom[node] = meet
                changed = True
    return idom


def _intersect(a: int, b: int, idom: dict[int, int], number: dict[int, int]) -> int:
    """The nearest node that dominates both ``a`` and ``b``."""
    while a != b:
        while number[a] < number[b]:
            a = idom[a]
        while number[b] < number[a]:
            b = idom[b]
    return a
