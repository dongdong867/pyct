"""Pinned positions: a split's piece a tracked operand handed out, an index say, is written
``["[]", split, ["pin", k, operand, value]]`` (``core.str_splits.pinned``): piece k, read only
while the operand has its value (keep-a-tracked-index-into-a-split-as-v2-does).

A fork on such a piece holds only there: the read is the piece while the pin's condition
holds and an item of its own, which no fork ties, where it does not, and the piece is there
only while the condition holds. The fork aimed at reads the piece where the run read it: its
pins' conditions are held (``aimed``)."""

from __future__ import annotations

from pyct.core.branch import Expression
from pyct.solver.list_kinds import ITEM_SORTS
from pyct.solver.list_slices import Slices
from pyct.solver.list_terms import TRUE, Lin, Piece, Read
from pyct.solver.literals import leaf_term

PIN = "pin"


class PinnedReads(Slices):
    """A list's positions and slices (``Slices``), its reads at pinned positions, and each
    pin's condition by its part, for ``ListTerms``, which reads an item at a position
    (``_read``)."""

    def __init__(self) -> None:
        Slices.__init__(self)
        self.pins: dict[int, str] = {}

    def pin(self, node: list[Expression]) -> str:
        """A pinned position's term, k's, noting its condition: the operand at its value, and
        any pin inside held."""
        _, at, operand, value = node
        assert type(value) is int
        held = f"(= {self.named(operand)} {leaf_term(value)})"
        if isinstance(at, list):
            held = f"(and {self.pins[id(at)]} {held})"
        self.pins[id(node)] = held
        return self.named(at)

    def item_at(self, piece: Piece, part: Expression, item: str) -> Read:
        """The item of that kind a read at ``part`` gives: at a pinned position, the item there
        while the pin's condition holds, and an item of its own where it does not."""
        position = unpinned(part)
        found = self._read(piece, self.position(position, piece), item)
        if position is part or found.value is None:
            return found
        pin = self.pins[id(part)]
        free = f"pinned!{len(self.definitions)}"
        self.definitions.append(f"(declare-const {free} {ITEM_SORTS[item]})")
        guard = TRUE if found.guard == TRUE else f"(=> {pin} {found.guard})"
        return Read(f"(ite {pin} {found.value} {free})", guard)

    def aimed(self, expression: Expression) -> list[str]:
        """The condition of each pinned position an expression reads, once each."""
        found: dict[str, None] = {}
        stack, seen = [expression] if self.pins else [], set()
        while stack:
            part = stack.pop()
            if isinstance(part, list) and id(part) not in seen:
                seen.add(id(part))
                if id(part) in self.pins:
                    found[self.pins[id(part)]] = None
                stack.extend(part[1:])
        return list(found)

    def _read(self, piece: Piece, position: Lin, item: str) -> Read:
        raise NotImplementedError


def unpinned(part: Expression) -> Expression:
    """The plain position a pinned one reads at, or the part itself."""
    while isinstance(part, list) and part[:1] == [PIN]:
        part = part[1]
    return part
