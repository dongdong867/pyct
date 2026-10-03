"""The splits' lists of one path: each split's count, how a compare reads it, the bound each is
tied to, and what the path's reads and ties say of the program (see ``split_lists``)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace

from pyct.core.branch import Branch, Expression
from pyct.core.str_splits import LISTED_SPLITS, measured_splits, splits_read_from_the_end
from pyct.solver.list_terms import Least, Lin, Read, both, compare, negated
from pyct.solver.literals import plain_operand
from pyct.solver.split_lists import BOUND_PAST, MOST_BOUND, SplitList

# what each compare of a length with a number, taken or not, says of the length: the least
# and the most it can be, by the number
_RANGES: Mapping[tuple[str, bool], Callable[[int], tuple[int, int | None]]] = {
    (">", True): lambda n: (n + 1, None),
    (">=", True): lambda n: (n, None),
    ("<", True): lambda n: (0, n - 1),
    ("<=", True): lambda n: (0, n),
    ("==", True): lambda n: (n, n),
    (">", False): lambda n: (0, n),
    (">=", False): lambda n: (0, n - 1),
    ("<", False): lambda n: (n, None),
    ("<=", False): lambda n: (n + 1, None),
    ("!=", False): lambda n: (n, n),
}

# each order read the other way round, for a number on the left
_FLIPPED = {"<": ">", "<=": ">=", ">": "<", ">=": "<=", "==": "==", "!=": "!="}

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
        # the largest number a fork compares each split's length with, and the least and the
        # most the forks on its own length let it be, by the split's part
        self.numbers: dict[int, int] = {}
        self.ranges: dict[int, tuple[int, int | None]] = {}
        # each split the path reads counted back from its end, by its part
        self.ended: set[int] = set()

    def learn(self, prefix: tuple[Branch, ...]) -> None:
        """The largest number a fork compares each split's list's length with, or the length
        of a list built from it."""
        for fork in prefix:
            expression = fork.expression
            self.ended.update(id(split) for split in splits_read_from_the_end(expression))
            if not isinstance(expression, list) or len(expression) != 3:
                continue
            numbers = [part for part in expression[1:] if type(part) is int]
            for split, start in measured_splits(expression):
                most = [number + start for number in numbers]
                self.numbers[id(split)] = max([self.numbers.get(id(split), 0), *most])
            self._range(expression, fork.taken)

    def _range(self, expression: list[Expression], taken: bool) -> None:
        """Narrow the least and the most a split's count can be by a fork that compares its
        own length with a number."""
        op, left, right = expression
        if type(left) is int:
            op, left, right = _FLIPPED.get(str(op), ""), right, left
        read = _RANGES.get((str(op), taken))
        if read is None or type(right) is not int or not _counts(left):
            return
        assert isinstance(left, list)
        low, high = read(right)
        was_low, was_high = self.ranges.get(id(left[1]), (0, None))
        highs = [value for value in (was_high, high) if value is not None]
        self.ranges[id(left[1])] = (max(was_low, low), min(highs) if highs else None)

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
        # the input's own count bounds only a list the path reads from its end, which may read
        # it there: tied to every piece of a long input, a count no fork needs that large ran
        # past the limit at 12 lines, and past 16 kept the input's own string
        own = held or 0 if id(node) in self.ended else 0
        most = max(self.numbers.get(id(node), 0), own) + BOUND_PAST
        bound = min(most, MOST_BOUND)
        count = f"count!{len(self.lists)}!"
        choose = self.back_among_counts
        known = text if isinstance(text, str) else None
        compared = self.numbers.get(id(node), 0)
        listed = SplitList(
            term, str(head), plain, count, bound, self.hold, held, choose, known, compared
        )
        listed = replace(listed, read_count=self._read_count(node, held))
        self.lists[listed.count] = listed
        self.parts[id(node)] = listed.count
        self.counts[listed.count] = listed.past
        return listed

    def _read_count(self, node: list[Expression], held: int | None) -> int | None:
        """The count a read from the end puts its piece at: the input's own, moved as little as
        the forks on the split's own length need."""
        if held is None:
            return None
        low, high = self.ranges.get(id(node), (0, None))
        count = max(held, low)
        return count if high is None else max(min(count, high), low)

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


def _counts(part: Expression) -> bool:
    """Whether a part is the length of a split's own list, ``["len", [split, ...]]``."""
    if not isinstance(part, list) or part[:1] != ["len"] or not isinstance(part[1], list):
        return False
    return part[1][:1] != [] and part[1][0] in LISTED_SPLITS
