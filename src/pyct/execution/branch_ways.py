"""The branches of one code object, and the lines their ways lead to, read from its bytecode.

A branch is a line whose tests can send the code on to two or more other
lines: an ``if``, a ``while`` or ``for`` test, or a condition spread over
lines. Each way is counted by the line it leads to, the next line a LINE
event names. The read follows a way through jumps and through the rest of
its own line, and stops at a raise, a return, or another test on the same
line, which counts its own ways; so two ways to the same line are one, and
a way that stays on its line counts none.

A comprehension laid out over lines has the compiler place code on the
element's line: the jump back to the loop, and from Python 3.13 the
filter's conditional jump itself. So a conditional jump that starts its
line's instructions, right after the code that computed its operand on
another line, belongs to that line; a way follows a jump placed after another instruction of a line
before it takes that line; and ``NOT_TAKEN``, which only marks a way for
``sys.monitoring``, names no line.

The tests are the instructions a ``sys.monitoring`` BRANCH event reports
(BRANCH_LEFT and BRANCH_RIGHT from Python 3.14): the conditional jumps and
``FOR_ITER``. An event names the test's offset and where it went, and
``CodeWays.way`` turns the two into the branch line and the line it led to.
"""

from __future__ import annotations

import dis
import types
from collections.abc import Mapping

# the jumps that always jump, which a way follows to their target
_JUMPS = frozenset(
    {"JUMP", "JUMP_BACKWARD", "JUMP_BACKWARD_NO_INTERRUPT", "JUMP_FORWARD", "JUMP_NO_INTERRUPT"}
)
# the instructions a way never goes past: the code ends or raises there
_ENDS = frozenset({"RAISE_VARARGS", "RERAISE", "RETURN_CONST", "RETURN_VALUE"})
# the instructions that only mark a way for sys.monitoring, from Python 3.14
_MARKS = frozenset({"NOT_TAKEN"})


def _is_test(instruction: dis.Instruction) -> bool:
    """Whether a BRANCH event reports the instruction: a conditional jump, or ``FOR_ITER``."""
    return instruction.opname.startswith("POP_JUMP_IF") or instruction.opname == "FOR_ITER"


class CodeWays:
    """One code object's lines and branches, and the way each BRANCH event in it went.

    ``lines`` is every line the code's line table names. ``branches`` maps
    each branch line to the lines its ways lead to, two or more of them.
    """

    def __init__(self, code: types.CodeType) -> None:
        # line 0 and no line both mark an instruction the compiler made, which no line names
        self._line_at = {
            offset: line or None
            for start, end, line in code.co_lines()
            for offset in range(start, end, 2)
        }
        instructions = list(dis.get_instructions(code))
        self._at = {instruction.offset: instruction for instruction in instructions}
        self._next = {
            instruction.offset: following.offset
            for instruction, following in zip(instructions, instructions[1:], strict=False)
        }
        self._before = {offset: before for before, offset in self._next.items()}
        self.lines = frozenset(line for _, _, line in code.co_lines() if line)
        self.branches: Mapping[int, frozenset[int]] = self._branches(instructions)
        # each event's way, read once: a loop reports the same test and target on every pass
        self._went: dict[tuple[int, int], tuple[int, int] | None] = {}

    def way(self, test: int, target: int) -> tuple[int, int] | None:
        """The branch line and the line the way to ``target`` led to, for a BRANCH event at
        ``test``. None when the test's line is no branch or the way stays on that line."""
        key = (test, target)
        if key not in self._went:
            line = self._test_line(test)
            leads = None if line not in self.branches else self._leads_to(line, target)
            self._went[key] = None if line is None or leads is None else (line, leads)
        return self._went[key]

    def _branches(self, instructions: list[dis.Instruction]) -> dict[int, frozenset[int]]:
        """Each line whose tests lead to two or more other lines, with those lines."""
        ways: dict[int, set[int]] = {}
        for instruction in instructions:
            line = self._test_line(instruction.offset)
            if line is None or not _is_test(instruction):
                continue
            targets = (self._next.get(instruction.offset), instruction.argval)
            leads = {self._leads_to(line, target) for target in targets}
            ways.setdefault(line, set()).update(lead for lead in leads if lead is not None)
        return {line: frozenset(leads) for line, leads in ways.items() if len(leads) > 1}

    def _leads_to(self, line: int, offset: object) -> int | None:
        """The first other line the code reaches from ``offset``, by jumps and the rest of
        ``line``. None at a raise, a return, or another test before any other line."""
        seen: set[int] = set()
        while isinstance(offset, int) and offset in self._at and offset not in seen:
            seen.add(offset)
            instruction = self._at[offset]
            at = self._line_of(offset)
            if at is not None and at != line and not self._passed(instruction, at):
                return at
            if instruction.opname in _JUMPS:
                offset = instruction.argval
            elif instruction.opname in _ENDS or _is_test(instruction):
                return None
            else:
                offset = self._next.get(offset)
        return None

    def _passed(self, instruction: dis.Instruction, line: int) -> bool:
        """Whether a way goes past the instruction on ``line`` rather than taking the line: a
        mark, or a jump the compiler placed after another instruction of the line."""
        if instruction.opname in _MARKS:
            return True
        before = self._before.get(instruction.offset)
        return instruction.opname in _JUMPS and before is not None and self._line_of(before) == line

    def _test_line(self, offset: int) -> int | None:
        """The line a test at ``offset`` belongs to: its own, or, for a conditional jump that
        starts its line's instructions, the line of the code before it that computed its
        operand. A loop's ``FOR_ITER`` keeps its own."""
        line = self._line_of(offset)
        before = self._before.get(offset)
        if self._at[offset].opname == "FOR_ITER" or before is None:
            return line
        if self._line_of(before) in (None, line):
            return line
        computed = self._at[before]
        if computed.opname in _JUMPS or computed.opname in _ENDS or _is_test(computed):
            return line
        return self._line_of(before)

    def _line_of(self, offset: int) -> int | None:
        """The line the instruction at ``offset`` belongs to, or None."""
        return self._line_at.get(offset)
