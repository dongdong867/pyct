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
from pyct.solver.split_lists import SplitList
from pyct.solver.split_paths import Splits

PIN = "pin"


class PinnedReads(Slices):
    """A list's positions and slices (``Slices``), its reads at pinned positions, and each
    pin's condition by its part, for ``ListTerms``, which reads an item at a position
    (``_read``)."""

    splits: Splits

    def __init__(self) -> None:
        Slices.__init__(self)
        self.pins: dict[int, str] = {}

    def pin(self, node: list[Expression]) -> str:
        """A pinned position's term, k's, noting its condition: the operand at its value, each
        split whose count the operand reads holding the count it had (c*), and any pin inside
        held. An operand that reads a count, ``len(parts) - n`` say, is that value only while
        the string has that many pieces."""
        _, at, operand, value = node
        assert type(value) is int
        held = [f"(= {self.named(operand)} {leaf_term(value)})", *self._counts_held(operand)]
        if isinstance(at, list):
            held.insert(0, self.pins[id(at)])
        self.pins[id(node)] = held[0] if len(held) == 1 else f"(and {' '.join(held)})"
        return self.named(at)

    def _counts_held(self, operand: Expression) -> list[str]:
        """That each split whose count the operand reads has the pieces c* says."""
        held: list[str] = []
        for listed in self.splits_counted(operand):
            if listed.read_count is not None:
                count = listed.read_count
                held += [listed.past(count - 1), f"(not {listed.past(count)})"]
        return [fact for fact in held if fact != TRUE]

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

    def splits_counted(self, part: Expression) -> list[SplitList]:
        """The splits whose own count a part reads, ``len(parts)`` in ``n % len(parts)``."""
        found: list[SplitList] = []
        stack, seen = [part], set()
        while stack:
            node = stack.pop()
            if not isinstance(node, list) or id(node) in seen:
                continue
            seen.add(id(node))
            count = self.splits.parts.get(id(node[1])) if node[:1] == ["len"] else None
            if count is not None:
                found.append(self.splits.lists[count])
            stack.extend(node[1:])
        return found


def unpinned(part: Expression) -> Expression:
    """The plain position a pinned one reads at, or the part itself."""
    while isinstance(part, list) and part[:1] == [PIN]:
        part = part[1]
    return part
