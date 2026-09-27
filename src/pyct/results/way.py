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
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from pyct.results.blocks import Op, Step, StepKind, blocks_of_code, exits, handler_ranges
from pyct.results.graphs import (
    Pace,
    dominators,
    intersect,
    never,
    postorder,
    strictly_after,
)


@dataclass(frozen=True)
class Place:
    """A step as a walk meets it: the side's node, and the node the side leaves."""

    step: Step
    node: int
    source: int


# a fork as the flow reads it: its line and column, the side it took, and whether it is an
# operation's before a raise
type Fork = tuple[int, int, bool, bool]


class Flow:
    """One function's blocks, sides and raises, with who dominates whom.

    ``raising`` holds the positions, ``(line, col)``, where a run recorded
    a fork before an operation that may raise; the instruction there is a
    condition whose true side goes on to the next instruction.
    """

    def __init__(
        self,
        code: types.CodeType,
        raising: frozenset[tuple[int, int]],
        late: Callable[[float], bool] = never,
    ) -> None:
        self.pace = Pace(late)
        graph = _Graph.of(code, raising, self.pace)
        self._graph = graph
        pace = self.pace
        order = postorder(graph.successors, graph.entry, pace=pace)
        self._order = {n: at for at, n in enumerate(order)}
        self._idom = dominators(graph.successors, graph.entry, self._order, pace)
        self._normal = frozenset(postorder(graph.normal, graph.entry, pace=pace))
        # one line's searches, kept while its cause is worked out: kept for every line they
        # would grow as lines times nodes
        self._reaching_lines: dict[int, frozenset[int]] = {}
        self._towards: dict[int, frozenset[int]] = {}

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
            self.pace.step()
            self._mark_up(self._meet_of(self._holders(line)), found)
        for fork in set(forks):
            self.pace.step()
            self._mark_up(self._meet_of(self._proved_by.get(fork, [])), found)
        return frozenset(found)

    def _mark_up(self, node: int | None, found: set[int]) -> None:
        """Add ``node`` and every node that dominates it, stopping at one already found:
        everything above that is found too, so a run's lines cost its path, not its depth."""
        while node is not None and node not in found:
            self.pace.step()
            found.add(node)
            node = None if node == self._graph.entry else self._idom[node]

    @functools.cached_property
    def _by_lines(self) -> frozenset[int]:
        """The nodes some line could prove a run passed, were it covered."""
        return self.marked(self._graph.lines(), ())

    @functools.cached_property
    def _by_forks(self) -> dict[int, frozenset[tuple[int, int, bool]]]:
        """Each node, and up to two of the tests whose forks could prove a run passed it.

        A test's fork proves every node that dominates its side, so a node's
        tests are those in its part of the dominator tree. Two are enough to
        tell whether one other than a given test is among them. One pass up
        the tree: a node's descendants finish before it in the flow's
        postorder, since whatever dominates a node is on every way to it.
        """
        steps = self._graph.steps
        held: dict[int, set[tuple[int, int, bool]]] = {}
        for node in sorted(self._idom, key=self._order.__getitem__):
            self.pace.step()
            tests = held.setdefault(node, set())
            step = steps.get(node)
            if step is not None and step.kind is StepKind.CONDITION and len(tests) < 2:
                tests.add((step.line, step.col, step.raising))
            parent = self._idom[node]
            if parent != node:
                _keep_two(held.setdefault(parent, set()), tests)
        return {node: frozenset(tests) for node, tests in held.items()}

    def knowable(self, place: Place) -> bool:
        """Whether a run could show it took this side, when the side's own test forks nowhere.

        It can when a line only this side leads to is covered, or another test
        only this side leads to records a fork. The sides of a ternary, which
        join again at once, show nothing.
        """
        step = place.step
        own = (step.line, step.col, step.raising)
        others = self._by_forks.get(place.node, frozenset()) - {own}
        return place.node in self._by_lines or bool(others)

    def only_in_handlers(self, line: int) -> bool:
        """Whether only a raise reaches ``line``: no block that holds it runs without one."""
        holders = self._graph.blocks_of(line)
        return bool(holders) and not any(block in self._normal for block in holders)

    def yield_lines(self) -> frozenset[int]:
        """The lines that hold a yield: a ``yield``, a ``yield from`` or an ``await``."""
        return frozenset(self._graph.yields.values())

    def reaching_lines(self, line: int) -> frozenset[int]:
        """The lines a run can go on from to ``line``, found by one search back from it."""
        if line not in self._reaching_lines:
            held = self._graph.held
            toward = self._toward(line) - set(self._holders(line))
            self._reaching_lines = {
                line: frozenset(at for node in toward for at in held.get(node, ()))
            }
        return self._reaching_lines[line]

    def last_among(self, ran: frozenset[int]) -> frozenset[int]:
        """The lines of ``ran`` that no other line of ``ran`` comes strictly after.

        Strictly after is a later part of the flow a run cannot come back from:
        lines in one loop are not after each other, and a line is not after
        itself though Python compiles it into several blocks, as an ``await``.
        One pass forward and one back over the flow's loops taken as single
        parts, with each part's lines as the bits of an int.
        """
        part, following, preceding = self._parts
        lines = sorted(ran)
        each_line = self.pace.each
        parts_of = {
            line: {part[b] for b in self._holders(line) if b in part} for line in each_line(lines)
        }
        held = [0] * len(following)
        for at, line in enumerate(each_line(lines)):
            for each in parts_of[line]:
                held[each] |= 1 << at
        later = [0] * len(following)
        for each in reversed(range(len(following))):
            self.pace.step()
            for next_ in following[each]:
                later[each] |= held[next_] | later[next_]
        earlier = [0] * len(following)
        for each in range(len(following)):
            self.pace.step()
            for back in preceding[each]:
                earlier[each] |= held[back] | earlier[back]
        return frozenset(
            line
            for at, line in enumerate(each_line(lines))
            if not strictly_after(parts_of[line], (held, later, earlier)) & ~(1 << at)
        )

    @functools.cached_property
    def _parts(self) -> tuple[dict[int, int], list[set[int]], list[set[int]]]:
        """Each reachable node's strongly connected part, numbered in the order a run meets
        them, and each part's following and preceding parts (Kosaraju's two passes)."""
        part = self._part_of()
        count = max(part.values(), default=-1) + 1
        following: list[set[int]] = [set() for _ in range(count)]
        preceding: list[set[int]] = [set() for _ in range(count)]
        graph = self._graph
        for node, at in part.items():
            self.pace.step()
            for next_ in graph.successors[node]:
                if part.get(next_, at) != at:
                    following[at].add(part[next_])
                    preceding[part[next_]].add(at)
        return part, following, preceding

    def _part_of(self) -> dict[int, int]:
        """Each reachable node's strongly connected part, numbered in the order a run meets
        them: Kosaraju's second pass, back from each node in the order the flow finishes them."""
        before = self._predecessors
        part: dict[int, int] = {}
        number = -1
        for root in sorted(self._order, key=self._order.__getitem__, reverse=True):
            if root in part:
                continue
            number += 1
            part[root] = number
            stack = [root]
            while stack:
                self.pace.step()
                node = stack.pop()
                for back in before[node]:
                    if back in self._order and back not in part:
                        part[back] = number
                        stack.append(back)
        return part

    def straight(self, start: int, line: int) -> bool:
        """Whether a run that ran ``start`` goes on to ``line`` with no condition, no raise and
        no yield between them, so only a raise or an ending could keep it from the line.

        From every block that holds ``start``: a line such as a ternary's holds
        the blocks on both sides of its test, and a run in the first may not
        have gone on at all. A frame can stay at a yield, so a run stops there.
        """
        ends = set(self._holders(line))
        holders = self._holders(start)
        return bool(holders) and all(
            ends.intersection(postorder(self._plain, *self._plain[block], pace=self.pace))
            for block in holders
        )

    @functools.cached_property
    def _plain(self) -> list[list[int]]:
        """Each node's successors a run reaches with no condition, no raise and no yield."""
        graph = self._graph
        return [
            [] if node in graph.yields else [each for each in following if each not in graph.steps]
            for node, following in enumerate(graph.successors)
        ]

    def run_of(self, line: int) -> tuple[int, ...]:
        """The first block of the straight run that holds ``line``: its lines share a cause.

        A block whose one way in is the one plain way out of the block before
        it, with no condition or yield between, is reached exactly when that
        block goes on, so every line along such a run has the same way and the
        same reaching sides. A raise out of the block before is no way in.
        """
        holders = self._holders(line)
        if len(holders) != 1:
            return tuple(sorted(holders))
        block = holders[0]
        before = self._predecessors
        blocks = [node for node in before[block] if node not in self._graph.steps]
        while len(before[block]) == 1 and len(blocks) == 1 and self._plain[blocks[0]] == [block]:
            block = blocks[0]
            blocks = [node for node in before[block] if node not in self._graph.steps]
        return (block,)

    @functools.cached_property
    def _proved_by(self) -> dict[Fork, list[int]]:
        """Each fork the code can record, and the nodes it proves: the side it took, or, for an
        operation that raised, its block, the side's one predecessor. Built once, read per fork."""
        proved: dict[Fork, list[int]] = {}
        before = self._predecessors
        for node, step in self._graph.steps.items():
            self.pace.step()
            if step.kind is not StepKind.CONDITION:
                continue
            proved.setdefault((step.line, step.col, step.side, step.raising), []).append(node)
            if step.raising:
                proved.setdefault((step.line, step.col, False, True), []).append(before[node][0])
        return proved

    @functools.cached_property
    def _predecessors(self) -> list[list[int]]:
        return self._graph.predecessors()

    def raises_toward(self, line: int) -> frozenset[int]:
        """The raise nodes entered from a block ``line`` can still be reached from."""
        toward = self._toward(line)
        before = self._predecessors
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
        return functools.reduce(
            lambda a, b: intersect(a, b, self._idom, self._order, self.pace), reachable
        )

    def _up(self, node: int) -> list[int]:
        """``node`` and every node that dominates it, nearest first."""
        found = [node]
        while node != self._graph.entry:
            node = self._idom[node]
            found.append(node)
        return found

    def _toward(self, line: int) -> frozenset[int]:
        if line not in self._towards:
            self._towards = {
                line: frozenset(postorder(self._predecessors, *self._holders(line), pace=self.pace))
            }
        return self._towards[line]

    def _tested_before(self, node: int) -> tuple[int, int]:
        """Test order: the node a side leaves, earliest first, then the side's own number."""
        return (-self._order[self._idom[node]], node)


def _keep_two(into: set[tuple[int, int, bool]], tests: set[tuple[int, int, bool]]) -> None:
    """Add ``tests`` to ``into`` until it holds two different ones."""
    for test in tests:
        if len(into) >= 2:
            return
        into.add(test)


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
    def of(cls, code: types.CodeType, raising: frozenset[tuple[int, int]], pace: Pace) -> _Graph:
        blocks, splits = blocks_of_code(code, raising, pace)
        builder = _Builder(blocks)
        for index, block in enumerate(blocks):
            pace.step()
            for target, step in exits(block, blocks, index, splits):
                builder.join(index, builder.block_at(target), step)
        ranges = list(handler_ranges(code, blocks))
        for start, covered in ranges:
            pace.step()
            if blocks[builder.block_at(start)][0].name == "END_ASYNC_FOR":
                builder.ends_an_async_for(start, covered)
        normal = [list(each) for each in builder.successors]
        for start, covered in ranges:
            pace.step()
            if blocks[builder.block_at(start)][0].name != "END_ASYNC_FOR":
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
        return self._by_line.get(line, [])

    @functools.cached_property
    def _by_line(self) -> dict[int, list[int]]:
        """Each line's blocks, indexed once."""
        indexed: dict[int, list[int]] = {}
        for block, lines in self.held.items():
            for line in lines:
                indexed.setdefault(line, []).append(block)
        return indexed

    def lines(self) -> set[int]:
        return {line for lines in self.held.values() for line in lines}

    def predecessors(self) -> list[list[int]]:
        before: list[list[int]] = [[] for _ in self.successors]
        for node, following in enumerate(self.successors):
            for each in following:
                before[each].append(node)
        return before


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

    def ends_an_async_for(self, start: int, covered: Iterable[int]) -> None:
        """An ``async for``'s end: the loop running out, the false side of its step.

        Python ends the loop by a raise into its END_ASYNC_FOR block; the side is
        the loop's own, at the iterable's column as a plain ``for``'s is.
        """
        target = self.block_at(start)
        ending = self.blocks[target][0]
        into = self.node()
        self.steps[into] = Step(StepKind.CONDITION, ending.line or 0, ending.col or 0, False)
        self.successors[into].append(target)
        for offset in covered:
            self.successors[self.block_at(offset)].append(into)

    def held(self) -> dict[int, frozenset[int]]:
        return {
            index: frozenset(op.line for op in block if op.line)
            for index, block in enumerate(self.blocks)
        }
