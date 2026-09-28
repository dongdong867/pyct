"""A function's instructions cut into basic blocks, and where each block goes on to.

The pieces ``way`` builds a function's flow from: which instructions test a
value, where a block ends, the step each way out of a block passes, and
which blocks each handler's range covers.
"""

from __future__ import annotations

import bisect
import dis
import types
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum

from pyct.results.graphs import Pace

# the jumps that test a value: `if`, `while`, `and`, `or`, `assert`, a ternary, a comprehension's
# `if`, and the test `is None` compiles to; a for loop's next item is its own two-way test
TESTS = frozenset(
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
# the compares a truth test may read the value of, whose argument 1 is `not in` or `is not`,
# and what may sit between the two and leaves the value as it is
_COMPARES = frozenset({"CONTAINS_OP", "IS_OP"})
_PASSED = frozenset({"COPY", "TO_BOOL", "NOP", "EXTENDED_ARG"})
# the tests of a value's truth, which may read an `in` or an `is`
_TRUTH = frozenset({"POP_JUMP_IF_FALSE", "POP_JUMP_IF_TRUE"})
# what an `except` clause tests the raise against: the jump after it is the clause's match
_MATCHES = frozenset({"CHECK_EXC_MATCH", "CHECK_EG_MATCH"})
# where a block's run ends with no way on
_ENDS = frozenset({"RETURN_VALUE", "RETURN_CONST", "RAISE_VARARGS", "RERAISE"})
_JUMPS = frozenset(dis.opname[op] for op in {*dis.hasjrel, *dis.hasjabs})


class StepKind(StrEnum):
    """What a step on a line's way is."""

    # a place that tests a value for truth, or a fork before an operation that may raise
    CONDITION = "condition"
    # the way into a handler: a raise reaching it, or an except clause matching the raise
    HANDLER = "handler"


@dataclass(frozen=True)
class Step:
    """One place on a line's way, and the side of it the line needs.

    ``raising`` marks a fork before an operation that may raise, whose true
    side goes on past the operation; a test at the same column is another step.
    ``reads`` is the `in` or `is` compare a truth test reads, whose side may
    then be read the other way (`pyct.results.senses`). It is no part of the step.
    """

    kind: StepKind
    line: int
    col: int
    side: bool
    raising: bool = False
    reads: Reads | None = field(default=None, compare=False)


@dataclass(frozen=True)
class Reads:
    """The `in` or `is` compare a truth test reads, as the code compiled it.

    ``negated`` is `not in` or `is not`, the compare's argument 1, and
    ``flag`` the True or False an `is` compares with, when the code loads it
    as a constant on either side, else None.
    """

    name: str
    negated: bool
    flag: bool | None = None


@dataclass(frozen=True)
class Op:
    """One instruction, as the flow reads it."""

    offset: int
    name: str
    target: int | None
    line: int | None
    col: int | None
    arg: int | None = None
    # where the instruction's source ends, the True or False a LOAD_CONST pushes, and the
    # compare a truth test reads
    end: tuple[int, int] | None = None
    flag: bool | None = None
    reads: Reads | None = None

    @property
    def at(self) -> tuple[int, int] | None:
        """Where the instruction's source starts, or None when it has no position."""
        return None if self.line is None or self.col is None else (self.line, self.col)


# every opcode dis lists as a jump: `hasjump` from 3.13, `hasjrel` and `hasjabs` before it. Pseudo
# opcodes, numbered past a byte, never appear in a code's bytes
_JUMP_OPCODES = frozenset(
    opcode
    for name in ("hasjump", "hasjrel", "hasjabs")
    for opcode in getattr(dis, name, ())
    if opcode < 256
)
# what the label pass is allowed for each pair of jumps, in seconds. It compares half the pairs,
# at about 2.5 ns each on 3.12 and 3.13 and 4.6 ns on 3.14, measured at 20000 `if`s on an Apple
# M-series; 10 ns for every pair is 20 ns for each one compared, four times the slowest
_A_PAIR = 1e-8


# one way out of a block: the offset it goes to, and the step it passes, if any
type Exit = tuple[int, Step | None]


def blocks_of_code(
    code: types.CodeType, raising: frozenset[tuple[int, int]], pace: Pace
) -> tuple[list[list[Op]], frozenset[int]]:
    """The code's blocks, and the offsets a raising operation's fork splits a block after.

    Reading a large function's instructions is the first work that grows, so
    ``pace`` steps once an instruction. Before the first, dis finds every
    jump's label in one pass no step can break into, so the pace is asked
    first whether that pass fits before the stop.
    """
    pace.afford(_label_pass(code))
    ops: list[Op] = []
    for instruction in _read(code, pace):
        ops.append(_op(instruction, ops))
    splits = _splits(ops, raising)
    edges = {edge for entry in _table(code) for edge in (entry.start, entry.end, entry.target)}
    return _blocks(ops, edges, splits), splits


def handler_ranges(code: types.CodeType, blocks: list[list[Op]]) -> Iterator[tuple[int, list[int]]]:
    """Each handler's first offset, and the first offset of every block its ranges cover."""
    starts = [block[0].offset for block in blocks]
    covered: dict[int, list[int]] = {}
    for entry in _table(code):
        # the blocks are in offset order, so each range is one slice of them
        inside = starts[
            bisect.bisect_left(starts, entry.start) : bisect.bisect_left(starts, entry.end)
        ]
        covered.setdefault(entry.target, []).extend(inside)
    yield from covered.items()


def _table(code: types.CodeType) -> list[dis._ExceptionTableEntry]:  # pyrefly: ignore[missing-attribute]
    # the code's exception table, which dis reads since 3.11 and typeshed leaves out
    return list(dis.Bytecode(code).exception_entries)  # pyrefly: ignore[missing-attribute]


def _label_pass(code: types.CodeType) -> float:
    """At most how long dis's label pass takes, in seconds.

    The pass checks each jump's label against every label it found before, so
    it grows as the square of the jumps. Each opcode is one byte in two of the
    code, and a jump opcode is one dis lists as a jump on this Python.
    """
    opcodes = code.co_code[::2]
    jumps = sum(opcodes.count(opcode) for opcode in _JUMP_OPCODES)
    return jumps * jumps * _A_PAIR


def _read(code: types.CodeType, pace: Pace) -> Iterator[dis.Instruction]:
    for instruction in dis.get_instructions(code):
        pace.step()
        yield instruction


def _op(instruction: dis.Instruction, before: list[Op]) -> Op:
    """One instruction, a truth test with the compare it reads among the ones ``before`` it."""
    positions = instruction.positions
    target = instruction.argval if instruction.opname in _JUMPS else None
    value = instruction.argval
    return Op(
        offset=instruction.offset,
        name=instruction.opname,
        target=target if isinstance(target, int) else None,
        line=None if positions is None else positions.lineno,
        col=None if positions is None else positions.col_offset,
        arg=instruction.arg,
        end=_end(positions),
        flag=value if instruction.opname == "LOAD_CONST" and isinstance(value, bool) else None,
        reads=_reads(instruction, before),
    )


def _reads(instruction: dis.Instruction, before: list[Op]) -> Reads | None:
    """The `in` or `is` compare a truth test reads, the last instruction before it in code order
    but for any that pass its value on, or None."""
    if instruction.opname not in _TRUTH:
        return None
    at = len(before) - 1
    while at >= 0 and before[at].name in _PASSED:
        at -= 1
    if at < 0 or before[at].name not in _COMPARES:
        return None
    compare = before[at]
    return Reads(compare.name, compare.arg == 1, _flag(before, at))


def _end(positions: dis.Positions | None) -> tuple[int, int] | None:
    if positions is None or positions.end_lineno is None or positions.end_col_offset is None:
        return None
    return positions.end_lineno, positions.end_col_offset


def _flag(before: list[Op], compare: int) -> bool | None:
    """The True or False the code loads as a compare's whole right operand, or its whole left.

    Read from the compare's own source span, which its operands' instructions
    lie inside: the right operand alone is the constant loaded right before the
    compare that ends where the compare ends, and the left one alone is the one
    instruction of the compare that starts where the compare starts. Anything
    else, a constant inside a larger operand or an operand the span does not
    show whole, is no constant.
    """
    op = before[compare]
    if op.line is None or op.col is None or op.end is None:
        return None
    start, end = (op.line, op.col), op.end
    right = before[compare - 1] if compare else None
    if right is not None and right.flag is not None and right.end == end:
        return right.flag
    starting = [each for each in _inside(before, compare, start, end) if each.at == start]
    return starting[0].flag if len(starting) == 1 else None


def _inside(
    before: list[Op], compare: int, start: tuple[int, int], end: tuple[int, int]
) -> list[Op]:
    """The instructions right before a compare whose source lies inside its span, back to the
    first that does not."""
    found: list[Op] = []
    for at in range(compare - 1, -1, -1):
        each = before[at]
        if each.at is None or each.end is None or each.at < start or each.end > end:
            break
        found.append(each)
    return found


def _splits(ops: list[Op], raising: frozenset[tuple[int, int]]) -> frozenset[int]:
    """The offsets of the instructions a raising operation's fork sits on.

    Several instructions of one expression start where it starts, such as the
    ``10`` and the ``//`` of ``10 // d``; the fork is the operation's, which
    runs last, so it is the last of them in each run of one line. A test's
    jump at the same column is the test's, never the operation's, and so is
    the ``NOT_TAKEN`` 3.14 puts after it, at the test's place.
    """
    found: set[int] = set()
    line: int | None = None
    seen: set[int | None] = set()
    for op in reversed(ops):
        if op.line != line:
            line, seen = op.line, set()
        if op.name in TESTS or op.name == "NOT_TAKEN":
            continue
        if (op.line, op.col) in raising and op.col not in seen:
            found.add(op.offset)
        seen.add(op.col)
    return frozenset(found)


def _blocks(ops: list[Op], edges: set[int], splits: frozenset[int]) -> list[list[Op]]:
    """The instructions cut where a jump lands, after a jump, an end or a split, at each edge
    of a handler's range, and where a new line starts.

    One line to a block, so a covered line proves its own block ran and no more: the
    line before a test that raised does not prove the test ran.
    """
    starts = {ops[0].offset, *edges}
    starts |= {op.target for op in ops if op.target is not None}
    for op, after in zip(ops, ops[1:], strict=False):
        if op.name in _JUMPS or op.name in _ENDS or op.offset in splits:
            starts.add(after.offset)
    blocks: list[list[Op]] = []
    line: int | None = None
    for op in ops:
        if op.offset in starts or not blocks or (op.line and line and op.line != line):
            blocks.append([])
            line = None
        blocks[-1].append(op)
        line = line or op.line
    return blocks


def exits(
    block: list[Op], blocks: list[list[Op]], index: int, splits: frozenset[int]
) -> Iterator[Exit]:
    """Where a block goes on to, and the step each way passes."""
    last = block[-1]
    after = blocks[index + 1][0].offset if index + 1 < len(blocks) else None
    if last.name in _ENDS:
        return
    if last.name in TESTS and last.target is not None and after is not None:
        yield from _test_exits(block, last.target, after)
        return
    if last.target is not None:
        yield last.target, None
        if last.name.startswith("JUMP"):
            return
    # the compiler ends every code on a return, a raise or a jump, so a last block goes nowhere
    if after is None:  # pragma: no cover
        return
    if last.offset in splits and last.line is not None and last.col is not None:
        yield after, Step(StepKind.CONDITION, last.line, last.col, True, raising=True)
        return
    yield after, None


def _test_exits(block: list[Op], jump: int, after: int) -> Iterator[Exit]:
    """A test's two sides as conditions; an except clause's match as a step on its true side."""
    last = block[-1]
    jumps_on = last.name in _JUMPS_WHEN_TRUE
    matching = len(block) > 1 and block[-2].name in _MATCHES
    for target, side in ((jump, jumps_on), (after, not jumps_on)):
        if matching:
            yield target, Step(StepKind.HANDLER, last.line or 0, 0, True) if side else None
        else:
            step = Step(StepKind.CONDITION, last.line or 0, last.col or 0, side, reads=last.reads)
            yield target, step


# CPython's flag on a function's code; a module and a class body run without it
_OPTIMIZED = 0x1


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
