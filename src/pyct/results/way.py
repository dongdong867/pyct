"""A line's way: the conditions every run of its function passes to reach the line.

Read from the compiled code, not the source, so an early ``return`` counts:
the lines after ``if x: return`` need the test's false side, which the
nesting of the source does not show (decision
why-missed-first-untaken-condition-from-control-flow). A function's flow
is its basic blocks joined by their jumps, with exception edges left out;
each ``except`` block, reached only by a raise, hangs off a root of its
own. A condition's two sides are nodes of their own between its block and
the next, so "every run passes this side" is "this node dominates the
line".
"""

from __future__ import annotations

import dis
import functools
import types
from collections.abc import Iterator
from dataclasses import dataclass
from enum import StrEnum

# the jumps that test a value: `if`, `while`, `and`, `or`, `assert`, a ternary, a comprehension's
# `if`, and the test `is None` compiles to; a for loop's next item is its own two-way test
_TESTS = frozenset(
    {
        "POP_JUMP_IF_FALSE",
        "POP_JUMP_IF_TRUE",
        "POP_JUMP_IF_NONE",
        "POP_JUMP_IF_NOT_NONE",
        "FOR_ITER",
    }
)
# a test jumps on its true side only here; every other one falls through into its true side
_JUMPS_WHEN_TRUE = frozenset({"POP_JUMP_IF_TRUE"})
# what an `except` clause tests the raise against: the jump after it is the clause's match
_MATCHES = frozenset({"CHECK_EXC_MATCH", "CHECK_EG_MATCH"})
# where a block's run ends with no way on
_ENDS = frozenset({"RETURN_VALUE", "RETURN_CONST", "RAISE_VARARGS", "RERAISE"})
_JUMPS = frozenset(dis.opname[op] for op in {*dis.hasjrel, *dis.hasjabs})
# CPython's flag on a function's code; a module and a class body run without it
_OPTIMIZED = 0x1


class StepKind(StrEnum):
    """What a step on a line's way is."""

    # a place that tests a value for truth, or a fork before an operation that may raise
    CONDITION = "condition"
    # the way into an except block: the raise reaching it, or the clause matching the raise
    HANDLER = "handler"


@dataclass(frozen=True)
class Step:
    """One place on a line's way, and the side of it the line needs.

    ``reaches`` is the first line that side runs other than the step's own,
    or None when that side stays on the step's line until it next branches:
    a run that covered it went that way.
    """

    kind: StepKind
    line: int
    col: int
    side: bool
    reaches: int | None


@dataclass(frozen=True)
class _Op:
    """One instruction, as the flow reads it."""

    offset: int
    name: str
    target: int | None
    line: int | None
    col: int | None


# one way out of a block: the offset it goes to, and the step it passes, if any
type _Exit = tuple[int, Step | None]


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
    """One function's blocks and the sides between them, with who dominates whom.

    ``raising`` holds the positions, ``(line, col)``, where a run recorded
    a fork before an operation that may raise; the instruction there is a
    condition whose true side goes on to the next instruction. A position a
    test jump holds is that test's, never such a fork.
    """

    def __init__(self, code: types.CodeType, raising: frozenset[tuple[int, int]]) -> None:
        ops = [_op(instruction) for instruction in dis.get_instructions(code)]
        # where each except block starts: the code's exception table, which dis reads since 3.11
        # and typeshed leaves out
        table = dis.Bytecode(code).exception_entries  # pyrefly: ignore[missing-attribute]
        handlers = sorted({entry.target for entry in table})
        graph = _Graph.of(ops, handlers, _splits(ops, raising))
        self._graph = graph
        self._idom = _dominators(graph.successors, graph.root, graph.order)
        self._normal = _reachable(graph.successors, graph.entry)

    def way(self, line: int) -> tuple[Step, ...]:
        """The steps every run takes to reach ``line``, in the order it takes them."""
        holders = [block for block in self._graph.blocks_of(line) if block in self._idom]
        if not holders:
            return ()
        node = functools.reduce(self._meet, holders)
        chain: list[int] = []
        while node != self._graph.root:
            chain.append(node)
            node = self._idom[node]
        steps = self._graph.steps
        return tuple(steps[node] for node in reversed(chain) if node in steps)

    def only_in_handlers(self, line: int) -> bool:
        """Whether only a raise reaches ``line``: no block that holds it runs without one."""
        holders = self._graph.blocks_of(line)
        return bool(holders) and not any(block in self._normal for block in holders)

    def _meet(self, a: int, b: int) -> int:
        return _intersect(a, b, self._idom, self._graph.order)


def _op(instruction: dis.Instruction) -> _Op:
    positions = instruction.positions
    target = instruction.argval if instruction.opname in _JUMPS else None
    return _Op(
        offset=instruction.offset,
        name=instruction.opname,
        target=target if isinstance(target, int) else None,
        line=None if positions is None else positions.lineno,
        col=None if positions is None else positions.col_offset,
    )


def _splits(ops: list[_Op], raising: frozenset[tuple[int, int]]) -> frozenset[int]:
    """The offsets of the instructions a raising operation's fork sits on.

    Several instructions of one expression start where it starts, such as the
    ``10`` and the ``//`` of ``10 // d``; the fork is the operation's, which
    runs last, so it is the last of them in each run of one line.
    """
    tested = {(op.line, op.col) for op in ops if op.name in _TESTS}
    forked = raising - tested
    found: set[int] = set()
    line: int | None = None
    seen: set[int | None] = set()
    for op in reversed(ops):
        if op.line != line:
            line, seen = op.line, set()
        if (op.line, op.col) in forked and op.col not in seen:
            found.add(op.offset)
        seen.add(op.col)
    return frozenset(found)


@dataclass(frozen=True)
class _Graph:
    """The blocks and sides as numbered nodes: each node's successors, and each side's step.

    Nodes below ``len(starts)`` are blocks, by their first offset; the ones
    above are sides. ``root`` stands before the function's first block and
    before each except block, since a raise can reach one from anywhere.
    """

    successors: list[list[int]]
    steps: dict[int, Step]
    lines: dict[int, frozenset[int]]
    root: int
    entry: int
    order: dict[int, int]

    @classmethod
    def of(cls, ops: list[_Op], handlers: list[int], splits: frozenset[int]) -> _Graph:
        blocks = _blocks(ops, handlers, splits)
        builder = _Builder(blocks)
        for index, block in enumerate(blocks):
            for target, step in _exits(block, blocks, index, splits):
                builder.join(index, builder.block_at(target), step)
        root = builder.node()
        builder.successors[root].append(0)
        for start in handlers:
            builder.join(root, builder.block_at(start), builder.handler_step(start))
        order = {node: at for at, node in enumerate(_postorder(builder.successors, root))}
        return cls(builder.successors, builder.steps, builder.lines(), root, 0, order)

    def blocks_of(self, line: int) -> list[int]:
        return [block for block, lines in self.lines.items() if line in lines]


class _Builder:
    """Numbers the nodes as the graph is built."""

    def __init__(self, blocks: list[list[_Op]]) -> None:
        self.blocks = blocks
        self.starts = {block[0].offset: index for index, block in enumerate(blocks)}
        self.successors: list[list[int]] = [[] for _ in blocks]
        self.steps: dict[int, Step] = {}

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

    def handler_step(self, start: int) -> Step:
        """The way a raise takes into the except block that starts at ``start``."""
        first = _first_line(self.blocks[self.block_at(start)], None)
        return Step(StepKind.HANDLER, first or 0, 0, True, first)

    def lines(self) -> dict[int, frozenset[int]]:
        return {
            index: frozenset(op.line for op in block if op.line)
            for index, block in enumerate(self.blocks)
        }


def _blocks(ops: list[_Op], handlers: list[int], splits: frozenset[int]) -> list[list[_Op]]:
    """The instructions cut where a jump lands, after a jump or an end, and after a split."""
    starts = {ops[0].offset, *handlers}
    starts |= {op.target for op in ops if op.target is not None}
    for op, after in zip(ops, ops[1:], strict=False):
        if op.name in _JUMPS or op.name in _ENDS or op.offset in splits:
            starts.add(after.offset)
    blocks: list[list[_Op]] = []
    for op in ops:
        if op.offset in starts or not blocks:
            blocks.append([])
        blocks[-1].append(op)
    return blocks


def _exits(
    block: list[_Op], blocks: list[list[_Op]], index: int, splits: frozenset[int]
) -> Iterator[_Exit]:
    """Where a block goes on to, and the step each way passes."""
    last = block[-1]
    after = blocks[index + 1][0].offset if index + 1 < len(blocks) else None
    if last.name in _ENDS:
        return
    if last.name in _TESTS and last.target is not None and after is not None:
        yield from _test_exits(block, blocks, last.target, after)
        return
    if last.target is not None:
        yield last.target, None
        if last.name.startswith("JUMP"):
            return
    # the compiler ends every code on a return, a raise or a jump, so a last block goes nowhere
    if after is None:  # pragma: no cover
        return
    if last.offset in splits and last.line is not None and last.col is not None:
        first = _first_line(blocks[index + 1], last.line)
        yield after, Step(StepKind.CONDITION, last.line, last.col, True, first)
        return
    yield after, None


def _test_exits(
    block: list[_Op], blocks: list[list[_Op]], jump: int, after: int
) -> Iterator[_Exit]:
    """A test's two sides as conditions; an except clause's match as a step on its true side."""
    last = block[-1]
    jumps_on = last.name in _JUMPS_WHEN_TRUE
    matching = len(block) > 1 and block[-2].name in _MATCHES
    by_start = {each[0].offset: each for each in blocks}
    for target, side in ((jump, jumps_on), (after, not jumps_on)):
        first = _first_line(by_start[target], last.line)
        if matching:
            yield target, Step(StepKind.HANDLER, last.line or 0, 0, True, first) if side else None
        else:
            yield target, Step(StepKind.CONDITION, last.line or 0, last.col or 0, side, first)


def _first_line(block: list[_Op], other_than: int | None) -> int | None:
    """The first line a block runs other than ``other_than``, or None when it runs no other."""
    return next((op.line for op in block if op.line and op.line != other_than), None)


def _postorder(successors: list[list[int]], root: int) -> list[int]:
    """The nodes reachable from ``root``, each after every node it leads to first."""
    order: list[int] = []
    seen = {root}
    stack: list[tuple[int, Iterator[int]]] = [(root, iter(successors[root]))]
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


def _reachable(successors: list[list[int]], start: int) -> frozenset[int]:
    return frozenset(_postorder(successors, start))


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
