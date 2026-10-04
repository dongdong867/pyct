"""The splits' lists of one path: each split's count, how a compare reads it, the number c* it
is where it meets anything else, and whether a read held a string to c* pieces (see
``split_lists``)."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from pyct.core.branch import Branch, Expression
from pyct.solver.list_terms import Lin, Read, both, compare, negated
from pyct.solver.literals import plain_operand
from pyct.solver.split_counts import FARTHEST, condition, input_value, windowed, windows_past
from pyct.solver.split_lists import SplitList, SplitRead, UnknownCountError

# how each order on two ints reads as a compare of the lower with the higher: whether the
# operands swap, and whether they may be equal
_ORDERS: Mapping[str, tuple[bool, bool]] = {
    "<": (False, False),
    "<=": (False, True),
    ">": (True, False),
    ">=": (True, True),
}


class Splits:
    """The splits' lists of one path: each by its count's name and by its part, how a compare
    reads each count and each slice's length of one, and the number each is where a term of
    the program reads it."""

    def __init__(self) -> None:
        self.lists: dict[str, SplitList] = {}
        self.parts: dict[int, str] = {}
        self.counts: dict[str, Callable[[int], str]] = {}
        # each count's c*, each slice's length at it and each slice's start, by name, where the
        # input's values give c*
        self.values: dict[str, int] = {}
        self.emitted: list[str] = []
        # the value the input holds for a part it names as it is, a split's string say
        self.given: Callable[[Expression], object] = lambda part: None
        # whether a piece read from the end, where no walk of the reversed string reads it,
        # holds its string to c* pieces, and whether a read did
        self.fixed_reads = True
        self.fixed = False
        # what each fork on a split's own count, through plain arithmetic with plain ints,
        # says the count is, by the split's part
        self.conditions: dict[int, list[Callable[[int], bool]]] = {}
        # each slice's length that is its split's count less a plain start, wherever the slice
        # holds an item, by name: the split's count and the start
        self.tails: dict[str, tuple[str, int]] = {}
        # each slice's start that is where c* puts it, by name: the split and the slice; and
        # each slice's length, by name: the split and the slices it is cut by, in turn
        self.starts: dict[str, tuple[SplitList, slice]] = {}
        self.cuts: dict[str, tuple[SplitList, tuple[slice, ...]]] = {}

    def learn(self, prefix: tuple[Branch, ...]) -> None:
        """What each fork that compares a split's count, through plain arithmetic, with a plain
        int says of the count, the side it took included."""
        for fork in prefix:
            found = condition(fork)
            if found is not None:
                split, holds = found
                self.conditions.setdefault(id(split), []).append(holds)

    def made(self, node: list[Expression], term: str) -> SplitList:
        """A split's list, its string's term ``term``, with how many pieces Python makes of the
        string in the input whose path this is, where its value is known, and c*."""
        head, string, *operands = node
        plain = tuple(plain_operand(part) for part in operands)
        text = input_value(string, self.given)
        held = len(getattr(str, str(head))(text, *plain)) if isinstance(text, str) else None
        listed = SplitList(
            term=term,
            head=str(head),
            operands=plain,
            count=f"count!{len(self.lists)}!",
            input_count=held,
            read_count=self._read_count(node, held),
            fixed=self.fixed_reads,
        )
        self.lists[listed.count] = listed
        self.parts[id(node)] = listed.count
        self.counts[listed.count] = listed.past
        if listed.read_count is not None:
            self.values[listed.count] = listed.read_count
        return listed

    def _read_count(self, node: list[Expression], held: int | None) -> int | None:
        """c*: the input's own count, or the count nearest it that every fork on the split's
        count through plain arithmetic with a plain int allows."""
        if held is None:
            return None
        conditions = self.conditions.get(id(node), [])
        for away in range(FARTHEST):
            for near in (held + away, held - away):
                if near >= 0 and all(holds(near) for holds in conditions):
                    return near
        return held

    def sliced(self, length: Lin, bounds: list[Expression]) -> tuple[Lin, Lin]:
        """Where a slice of a split's list, or of a slice of one, starts, and its length, from
        the list's ``length``; core keeps only the slices ``str_splits.a_split_s_list`` takes.
        A start from the start, or the last item for a slice that steps back from the end, is
        exact on every string; any other start of a split's own list is a name of its own,
        which a read takes where c* puts it, the string held to c* pieces (see ``read``); the
        length is ``cut``'s."""
        start, stop, step = (*bounds, None, None, None)[:3]
        assert isinstance(start, int | None) and isinstance(stop, int | None)
        assert isinstance(step, int | None)
        name = length.atoms[0][0]
        listed, windows = (self.lists[name], ()) if name in self.lists else self.cuts[name]
        window = slice(start, stop, step)
        cut_length = self.cut(listed, (*windows, window))
        if not windows and stop is None and step != -1 and (start is None or start >= 0):
            # a slice that holds an item is that many pieces short of the split
            self.tails[cut_length.atoms[0][0]] = (listed.count, start or 0)
        if step == -1 and start is None:
            return length.minus(Lin(1)), cut_length
        if step != -1 and (start is None or start >= 0):
            return Lin(start or 0), cut_length
        assert not windows and listed.read_count is not None
        name = f"start!{len(self.values)}!"
        self.starts[name] = (listed, window)
        self.values[name] = window.indices(listed.read_count)[0]
        return Lin.of(name), cut_length

    def cut(self, listed: SplitList, windows: tuple[slice, ...]) -> Lin:
        """The length of a list cut from a split's by slices with plain bounds, one after
        another, as a name of its own that a compare with a number reads as whether a piece is
        there, exact on every string."""
        name = f"cut!{len(self.values)}!"
        self.counts[name] = lambda number: windows_past(listed.past, windows, number)
        self.cuts[name] = (listed, windows)
        if listed.read_count is not None:
            self.values[name] = windowed(windows, listed.read_count)
        return Lin.of(name)

    def read(self, listed: SplitList, position: Lin, kind: str) -> Read:
        """A split's piece at ``position``, noting whether the read held the string to c*."""
        started = self._started(listed, position, kind)
        read = started or listed.read(self._counted_back(position), kind)
        self.fixed |= read.fixes_the_count
        return read.found

    def _started(self, listed: SplitList, position: Lin, kind: str) -> SplitRead | None:
        """A piece read through a slice whose start is where c* puts it: there, the string held
        to c* pieces, or, with ``fixed_reads`` false, where the input's own count puts it with
        no count held, as origin/v2 reads it; None for any other position."""
        if len(position.atoms) != 1 or position.atoms[0][1] != 1 or kind != "str":
            return None
        start = self.starts.get(position.atoms[0][0])
        if start is None:
            return None
        window, count, own = start[1], listed.read_count, listed.input_count
        assert count is not None and own is not None
        if self.fixed_reads:
            return listed.held_at(window.indices(count)[0] + position.const)
        return SplitRead(listed.at(window.indices(own)[0] + position.const))

    def _counted_back(self, position: Lin) -> Lin:
        """A position counted back from the end of a slice that runs to the split's end, as
        the same position counted back from the split's own end: the slice holds the item read
        there, so it is that many pieces short of the split."""
        if len(position.atoms) != 1 or position.atoms[0][1] != 1:
            return position
        tail = self.tails.get(position.atoms[0][0])
        if tail is None:
            return position
        count, start = tail
        return Lin.of(count).plus(Lin(position.const - start))

    def flags(self) -> dict[str, bool]:
        """What a program's splits say of it: whether a read held a string to c* pieces, which
        an unsat or unknown answer asks again (see `solver.cvc5`)."""
        return {"fixed": self.fixed}

    def count_of(self, node: list[Expression]) -> str:
        """The name of a split's count."""
        return self.parts[id(node)]

    def reads(self, term: Lin) -> bool:
        """Whether a term adds a split's count."""
        return any(atom in self.counts for atom, _ in term.atoms)

    def compare(self, head: str, left: Lin, right: Lin) -> str | None:
        """``left head right`` where a side adds a split's count: whether the split holds a
        piece, where the other side is a number; None for any other compare.

        The least values the path's own forks give are not read here: this compare is one of
        those forks, which the program asserts.
        """
        if head not in (*_ORDERS, "==", "!=") or not (self.reads(left) or self.reads(right)):
            return None
        if head in ("==", "!="):
            below = compare(left, right, {}, or_equal=True, counts=self.counts)
            same = both(below, compare(right, left, {}, or_equal=True, counts=self.counts))
            return same if head == "==" else negated(same)
        swap, or_equal = _ORDERS[head]
        low, high = (right, left) if swap else (left, right)
        return compare(low, high, {}, or_equal=or_equal, counts=self.counts)

    def defined(self, lines: list[str]) -> list[str]:
        """Each count, each slice's length of one and each slice's start, that a line of the
        program reads as a term, as its c*: the number this run produced, worked out from the
        input's values. Core tracks a split's list only for a string the solver works out
        (``str_splits.worked_out``), so a count read with no c* is a miss, never a guess."""
        text = "\n".join(lines)
        written: list[str] = []
        for name in dict.fromkeys([*self.counts, *self.values]):
            if name in text and name not in self.emitted:
                if name not in self.values:
                    raise UnknownCountError(f"no input count for {name}")
                self.emitted.append(name)
                written.append(f"(define-fun {name} () Int {self.values[name]})")
        return written
