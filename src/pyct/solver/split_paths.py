"""The splits' lists of one path: each split's count, how a compare reads it, the bound each is
tied to, and what the path's reads and ties say of the program (see ``split_lists``)."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from pyct.core.branch import Branch, Expression
from pyct.core.str_splits import measured_splits
from pyct.solver.list_terms import Least, Lin, Read, both, compare, negated
from pyct.solver.literals import plain_operand
from pyct.solver.split_lists import BOUND_PAST, MOST_BOUND, SplitList

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
    reads each count, each count a term of the program reads, and the value the input holds
    for a part it names as it is (a string a split splits, say), which render gives."""

    def __init__(self) -> None:
        self.lists: dict[str, SplitList] = {}
        self.parts: dict[int, str] = {}
        self.counts: dict[str, Callable[[int], str]] = {}
        self.emitted: list[str] = []
        self.given: Callable[[Expression], object] = lambda part: None
        self.hold = True
        self.back_among_counts = False
        # whether a read from the end put its piece where the input's own few pieces put it,
        # and each count whose list the path reads from the end
        self.fixed_few = False
        self.backs: set[str] = set()
        # each count a tie or a read holds the program by, and whether the held program's own
        # forks need more pieces than a count's bound
        self.bounds: set[str] = set()
        self.refuted = False
        # the largest number a fork compares each split's length with, by the split's part
        self.numbers: dict[int, int] = {}

    def learn(self, prefix: tuple[Branch, ...]) -> None:
        """The largest number a fork compares each split's list's length with, or the length
        of a list built from it."""
        for fork in prefix:
            expression = fork.expression
            if not isinstance(expression, list) or len(expression) != 3:
                continue
            numbers = [part for part in expression[1:] if type(part) is int]
            for split, start in measured_splits(expression):
                most = [number + start for number in numbers]
                self.numbers[id(split)] = max([self.numbers.get(id(split), 0), *most])

    @property
    def bounded(self) -> bool:
        """Whether the program holds a count to its bound or reads a piece among those below."""
        return bool(self.bounds)

    def made(self, node: list[Expression], term: str) -> SplitList:
        """A split's list, its string's term ``term``, with how many pieces Python makes of the
        string in the input whose path this is, where the input holds it as it is."""
        head, string, *operands = node
        plain = tuple(plain_operand(part) for part in operands)
        text = self.given(string)
        held = len(getattr(str, str(head))(text, *plain)) if isinstance(text, str) else None
        most = max(self.numbers.get(id(node), 0), held or 0) + BOUND_PAST
        bound = min(most, MOST_BOUND)
        count = f"count!{len(self.lists)}!"
        choose = self.back_among_counts
        known = text if isinstance(text, str) else None
        listed = SplitList(term, str(head), plain, count, bound, self.hold, held, choose, known)
        self.lists[listed.count] = listed
        self.parts[id(node)] = listed.count
        self.counts[listed.count] = listed.past
        return listed

    def read(self, listed: SplitList, position: Lin, kind: str, least: Least) -> Read:
        """A split's piece at ``position``, noting whether the read holds the program."""
        read = listed.read(position, kind, least)
        if listed.from_the_end(position):
            self.backs.add(listed.count)
        if read.held:
            self.bounds.add(listed.count)
        self.fixed_few |= read.fixes_a_few
        return read.found

    def flags(self) -> dict[str, bool]:
        """What a program's splits say of it: that its held asks cannot be sat, and that a read
        from the end fixed a few pieces (see `solver.cvc5`)."""
        return {"refuted": self.refuted, "fixed_few": self.fixed_few}

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

    def tied(self, lines: list[str], least: Least) -> tuple[list[str], list[str]]:
        """Each count a line of the program reads, declared, and tied to its split's pieces;
        a tie may read another split's count, which is tied as well. A count held to a bound
        below the least its path's forks give it refutes the held program."""
        text = "\n".join(lines)
        pending = [count for count in self.lists if count in text]
        declared: list[str] = []
        ties: list[str] = []
        while pending:
            count = pending.pop()
            if count in self.emitted:
                continue
            self.emitted.append(count)
            listed = self.lists[count]
            tie, held = listed.tie(count in self.backs)
            if held:
                self.bounds.add(count)
                self.refuted |= least.get(count, 0) > listed.bound
            declared.append(f"(declare-const {count} Int)")
            ties += tie
            pending += [other for other in self.lists if other in "\n".join(tie)]
        return declared, ties
