"""A split's list as cvc5 reads it: how many pieces it holds, and the piece at a position.

``split``, ``rsplit`` and ``splitlines`` hand the target a tracked list whose form is the call
(follow-the-length-of-a-split). No term holds the list. Each piece is the term `splits` writes
for its position, and the list's length is how many pieces the string has, which no term of
SMT-LIB counts at once. So a compare of the length with a number is written as whether the
piece there is present: ``len(parts) > 2`` is that piece 2 is there, which `splits` already
writes for each form, exact for every string. That holds wherever the lists write such a
compare, a fork or the branch of a read.

Only a length that meets anything else, a clamp a slice writes, a tracked int, another split's
length, is a named count. On whitespace it is one term, the words the string has, exact on
every string. Otherwise it is tied to the pieces up to a bound: two past the largest number
the path compares a length with, or past the input's own count, at most `MOST_BOUND`. The
count is the number of pieces there below the bound, and the piece at the bound is not, so an
answer holds no more pieces than the bound.

A piece is read at a number from the start, at a number from the end, which a walk of the
reversed string reads where one does (`splits.right_piece`), and at any other position as a
choice among the pieces below the bound.

A program that holds a count to its bound, or reads a piece among those below it, says so
(``Splits.bounded``), and an unsat to it is asked once more loosened: each count tied only to
the pieces below the bound, with no bound on it, and no piece read among those below it. An
unsat to that is the path's, and anything else a miss that says it is not
(`solver.cvc5._loosened`). So a path that needs more pieces than the bound is never `unsat`.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from pyct.core.branch import Branch, Expression
from pyct.core.str_splits import LONGEST_WALK
from pyct.solver.list_reader import ProgramTooLargeError
from pyct.solver.list_terms import FALSE, TRUE, Least, Lin, Read, both, compare, negated, nested
from pyct.solver.literals import plain_operand
from pyct.solver.splits import (
    SPLITS,
    left_count,
    right_count,
    right_piece,
    split_piece,
    unwalked_bound,
    words_count,
    words_past,
)

# a piece always there, counted
TRUE_ONE = "1"

# how many pieces past the largest number the path compares a length with a count is tied to:
# one more than any fork asks for
BOUND_PAST = 2

# the most pieces a count is tied to, and a piece chosen among: the program grows with the
# square of the bound, since each piece is a walk to it, and past about ten a tie takes cvc5 to
# its limit anyway. A path that needs more is asked loosened (see the module docstring)
MOST_BOUND = 34

# how each order on two ints reads as a compare of the lower with the higher: whether the
# operands swap, and whether they may be equal
_ORDERS: Mapping[str, tuple[bool, bool]] = {
    "<": (False, False),
    "<=": (False, True),
    ">": (True, False),
    ">=": (True, True),
}


@dataclass(frozen=True)
class SplitList:
    """One split's list: the string's term, the method and its plain operands, the name its
    count goes by where a term reads it, and the most pieces that count is tied to.

    ``bounds`` is where the list notes its count when the program holds it to the bound, shared
    by the path's splits; with ``hold`` false the program is the loosened one, which holds no
    count to a bound and reads no piece among those below it.
    """

    term: str
    head: str
    operands: tuple[object, ...]
    count: str
    bound: int
    bounds: list[str]
    hold: bool = True

    def limit(self) -> int:
        """The limit a split or an rsplit was called with, -1 for none."""
        if self.head in ("split", "rsplit") and len(self.operands) > 1:
            limit = self.operands[1]
            return limit if isinstance(limit, int) else -1
        return -1

    def least(self) -> int:
        """The fewest pieces it has: one on a separator, and none on whitespace or lines."""
        return 0 if self.head == "splitlines" or self._words() else 1

    def past(self, number: int) -> str:
        """That it holds more pieces than ``number``: piece ``number`` is there, on any string.

        On whitespace, the string has that many words and one more, which one membership
        says. An rsplit past the walk has the split's pieces up to its limit.
        """
        if number < 0:
            return TRUE
        limit = self.limit()
        if 0 <= limit < number:
            return FALSE
        if self.head == "splitlines" or self._walked():
            return SPLITS[self.head](self.term, self.operands, number)[1]
        if self._words():
            return words_past(self.term, number)
        # the split's separators, found from the start, up to the limit
        return split_piece(self.term, self.operands[:1], number)[1]

    def restriction(self) -> str:
        """What a string must be for the pieces from the start to be Python's: an rsplit past
        the walk reads its pieces as the split's, which they are on a string with no more
        separators than its limit, or fewer words (``splits.unwalked_bound``)."""
        limit = self.limit()
        if self.head != "rsplit" or not limit > LONGEST_WALK:
            return TRUE
        separator = self.operands[0]
        return unwalked_bound(self.term, separator if isinstance(separator, str) else None, limit)

    def _walked(self) -> bool:
        """Whether it is an rsplit walked to its limit."""
        return self.head == "rsplit" and 0 <= self.limit() <= LONGEST_WALK

    def _words(self) -> bool:
        """Whether it splits on whitespace."""
        return self.head in ("split", "rsplit") and (not self.operands or self.operands[0] is None)

    def piece(self, index: int) -> str:
        """Piece ``index`` from the start."""
        return SPLITS[self.head](self.term, self.operands, index)[0]

    def fact(self) -> str:
        """What holds of the pieces on every string, for render to assert: an rsplit walked to
        its limit has as many pieces as the split with that limit, as each finds as many
        separators as fit side by side, or words, up to it. cvc5 does not work that out from a
        walk of the reversed string, and without it a path that also splits the string from the
        start ran past its limit."""
        if self.head != "rsplit" or not 0 <= self.limit() <= LONGEST_WALK:
            return TRUE
        counts = (right_count(self.term, self.operands), left_count(self.term, self.operands))
        return f"(= {counts[0]} {counts[1]})"

    def tie(self) -> list[str]:
        """What the count is: on whitespace, the words the string has, at most the limit's
        pieces; otherwise the pieces there below the bound, and none at it. Loosened, the count
        is only past each number below the bound where that piece is there."""
        if self._words():
            return [f"(assert (= {self.count} {self._words_count()}))"]
        beyond = self.past(self.bound)
        if beyond != FALSE and not self.hold:
            tied = [f"(= (> {self.count} {at}) {self.past(at)})" for at in range(self.bound)]
            return [f"(assert (>= {self.count} 0))", *(f"(assert {tie})" for tie in tied)]
        present = [self.past(at) for at in range(self.bound)]
        flags = [TRUE_ONE if there == TRUE else f"(ite {there} 1 0)" for there in present]
        kept = [flag for flag, there in zip(flags, present, strict=True) if there != FALSE]
        total = "0" if not kept else kept[0] if len(kept) == 1 else f"(+ {' '.join(kept)})"
        tied = [f"(assert (= {self.count} {total}))"]
        if beyond != FALSE:
            self.bounds.append(self.count)
            tied.append(f"(assert {negated(beyond)})")
        return tied

    def _words_count(self) -> str:
        """How many words the string has, at most one past the limit when there is one."""
        words, limit = words_count(self.term), self.limit()
        return words if limit < 0 else f"(ite (< {words} {limit + 1}) {words} {limit + 1})"

    def _bounded(self) -> None:
        """Note a piece chosen among those below the bound; the loosened program reads none."""
        if not self.hold:
            raise ProgramTooLargeError("a piece past a split's bound has no term")
        self.bounds.append(self.count)

    def read(self, position: Lin, kind: str, least: Least) -> Read:
        """The piece at ``position``, and when it is there."""
        if kind != "str":
            return Read(None, FALSE)
        number = position.number()
        if number is not None:
            return Read(self.piece(number), both(self.past(number), self.restriction()))
        back = self._from_the_end(position)
        if back is not None:
            walked = right_piece(self.term, self.head, self.operands, back)
            if walked is not None:
                return Read(walked, self.past(back))
            return self._counted_back(back)
        return self._chosen(position, least)

    def _from_the_end(self, position: Lin) -> int | None:
        """How far from the last piece a position is, 0 the last, when it is the count less a
        number; None for any other position."""
        if position.atoms == ((self.count, 1),) and position.const < 0:
            return -position.const - 1
        return None

    def _counted_back(self, back: int) -> Read:
        """Piece ``back`` from the end as the piece from the start it is for each count below
        the bound, chosen by which piece is the last there."""
        self._bounded()
        branches = [
            (both(self.past(at + back), negated(self.past(at + back + 1))), self.piece(at))
            for at in range(self.bound)
        ]
        kept = [(condition, value) for condition, value in branches if condition != FALSE]
        if not kept:
            return Read(None, FALSE)
        value = nested(kept[:-1], kept[-1][1])
        guard = both(self.past(back), negated(self.past(self.bound + back)))
        return Read(value, both(guard, self.restriction()))

    def _chosen(self, position: Lin, least: Least) -> Read:
        """The piece at a position a term writes, among those below the bound."""
        self._bounded()
        branches = [(f"(= {position.text()} {at})", self.piece(at)) for at in range(self.bound)]
        value = nested(branches[:-1], branches[-1][1])
        return Read(value, both(compare(position, Lin(self.bound), least), self.restriction()))


class Splits:
    """The splits' lists of one path: each by its count's name and by its part, how a compare
    reads each count, the most pieces a count is tied to, each count a term of the program
    reads, and the value the input holds for a part it names as it is (a string a split splits,
    say), which render gives."""

    def __init__(self) -> None:
        self.lists: dict[str, SplitList] = {}
        self.parts: dict[int, str] = {}
        self.counts: dict[str, Callable[[int], str]] = {}
        self.bound = BOUND_PAST
        self.emitted: list[str] = []
        self.given: Callable[[Expression], object] = lambda part: None
        self.hold = True
        self.bounds: list[str] = []

    def learn(self, prefix: tuple[Branch, ...]) -> None:
        """The most pieces a count is tied to: past every number a fork compares a length
        with, at most `MOST_BOUND`."""
        numbers = [0]
        for fork in prefix:
            expression = fork.expression
            if isinstance(expression, list) and len(expression) == 3 and _measures(expression):
                numbers += [part for part in expression[1:] if type(part) is int]
        self.bound = min(max(numbers) + BOUND_PAST, MOST_BOUND)

    @property
    def bounded(self) -> bool:
        """Whether the program holds a count to its bound or reads a piece among those below."""
        return bool(self.bounds)

    def made(self, node: list[Expression], term: str) -> tuple[SplitList, int | None]:
        """A split's list, its string's term ``term``, and how many pieces Python makes of the
        string in the input whose path this is, where the input holds it as it is."""
        head, string, *operands = node
        plain = tuple(plain_operand(part) for part in operands)
        text = self.given(string)
        held = len(getattr(str, str(head))(text, *plain)) if isinstance(text, str) else None
        bound = self.bound if held is None else max(self.bound, min(held + BOUND_PAST, MOST_BOUND))
        count = f"count!{len(self.lists)}!"
        listed = SplitList(term, str(head), plain, count, bound, self.bounds, self.hold)
        self.lists[listed.count] = listed
        self.parts[id(node)] = listed.count
        self.counts[listed.count] = listed.past
        return listed, held

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

    def tied(self, lines: list[str]) -> tuple[list[str], list[str]]:
        """Each count a line of the program reads, declared, and tied to its split's pieces;
        a tie may read another split's count, which is tied as well."""
        text = "\n".join(lines)
        pending = [count for count in self.lists if count in text]
        declared: list[str] = []
        ties: list[str] = []
        while pending:
            count = pending.pop()
            if count in self.emitted:
                continue
            self.emitted.append(count)
            tie = self.lists[count].tie()
            declared.append(f"(declare-const {count} Int)")
            ties += tie
            pending += [other for other in self.lists if other in "\n".join(tie)]
        return declared, ties


def _measures(expression: list[Expression]) -> bool:
    """Whether a fork compares a list's length, ``[op, ["len", items], n]`` either way round."""
    return any(isinstance(part, list) and part[:1] == ["len"] for part in expression[1:])
