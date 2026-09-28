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

A program that holds a count to its bound, reads a piece among those below it or at the
input's own count, or reads an rsplit past its walk on a string with no more separators than
its limit, says so (``Splits.bounded``), and an unsat to it is asked once more loosened: each
count tied only to the pieces below the bound, with no bound on it, and none of those reads, a
program that holds only what every string splitting as Python does meets. An unsat to that is
the path's, and anything else a miss that says it is not (`solver.cvc5._loosened`). So a path
that needs more pieces than the bound is never `unsat`. A held program whose own forks need
more pieces than its bound is not asked, and neither is its loosened one, whose asks for three
such paths each ran to the limit: the fork is `unknown` at once (``Splits.refuted``).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from pyct.core.branch import Branch, Expression
from pyct.core.str_splits import LONGEST_WALK, splits_built_from
from pyct.solver.list_terms import FALSE, TRUE, Least, Lin, Read, both, compare, negated, nested
from pyct.solver.literals import plain_operand
from pyct.solver.splits import (
    SPLITS,
    left_count,
    right_count,
    right_piece,
    separators_past,
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
# square of the bound, since each piece is a walk to it: uncapped, a read from the end of 1,000
# lines peaked at 2.9 GB. A path that needs more is asked loosened (see the module docstring)
MOST_BOUND = 34

# the largest number a compare of a separator split's count with a number is written as the
# walk to that piece, which cvc5 answers fastest beside the pieces a path reads and their int
# conversions; past it, as one membership, since a walk to 1,000 ran past the limit where the
# membership answered in 0.02 s
MOST_WALKED_PAST = 16

# the most pieces an input may have for a piece read from the end, where no walk of the
# reversed string finds it, to be chosen among every count below the bound once the read at
# the input's own count is unsat. The read at the input's count comes first on every input
# whose bound is past this: on cvc5 1.3.4 the last of 8 lines read there answered in 1.7 s,
# where chosen among 10 counts it ran past the limit, and the last of 12 lines chosen among 14
# took 6.1 s where the input's own took 1.3 s. An input with more pieces is read at its count
# alone, so a path that needs another count is a miss
MOST_CHOSEN_BACK = 8

# the largest bound a piece of an input with few pieces is chosen among, once the read at the
# input's count is unsat: the last of 3 lines chosen among 10 counts answered in 9.6 s at a
# load of 30, and among more ran past the limit, where the read at the input's count gives up
# at once
MOST_CHOSEN_BOUND = MOST_CHOSEN_BACK + 2


@dataclass(frozen=True)
class SplitRead:
    """A read of a split's piece: what it found, whether it holds the program, and whether it
    put the piece where the input's own few pieces put it."""

    found: Read
    held: bool
    fixes_a_few: bool


class LoosenedReadError(Exception):
    """A loosened program reads a piece only a held one writes: past a split's bound, at the
    input's count, or on a string an rsplit past its walk is held to. The ask is a miss."""


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
    count goes by where a term reads it, the most pieces that count is tied to, and how many
    pieces the input's own string has, where the input holds it as it is.

    With ``hold`` false the program is the loosened one, which holds no count to a bound and
    reads no piece a held program alone writes. A tie and a read each say whether they hold
    the program, and `Splits` notes it.
    """

    term: str
    head: str
    operands: tuple[object, ...]
    count: str
    bound: int
    hold: bool = True
    input_count: int | None = None
    back_among_counts: bool = False

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
            # lines, and an rsplit walked to its limit (at most 17 pieces), count by their walk
            return SPLITS[self.head](self.term, self.operands, number)[1]
        if self._words():
            return words_past(self.term, number)
        separator = self.operands[0]
        assert isinstance(separator, str)
        if number <= MOST_WALKED_PAST:
            return self._there(number)
        return separators_past(self.term, separator, number)

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

    def _there(self, index: int) -> str:
        """That piece ``index`` is there, as the walk that reads it writes it: the pieces a
        path takes out are asserted there by the same walk, which cvc5 answered faster beside
        the pieces themselves than one membership."""
        if index < 0:
            return TRUE
        if 0 <= self.limit() < index:
            return FALSE
        if self.head == "rsplit" and not self._walked():
            # the split's pieces from the start, whose count this rsplit has up to its limit;
            # the string it reads them on is the read's restriction, not the count's
            return split_piece(self.term, self.operands[:1], index)[1]
        return SPLITS[self.head](self.term, self.operands, index)[1]

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

    def tie(self) -> tuple[list[str], bool]:
        """What the count is: on whitespace, the words the string has, at most the limit's
        pieces; otherwise the pieces there below the bound, each by its walk, and none at it.
        Loosened, the count is only past each number below the bound where that piece is there.
        A tie by walks answered where one by memberships ran past the limit beside a slice.
        Says whether it holds the count to the bound."""
        if self._words():
            return [f"(assert (= {self.count} {self._words_count()}))"], False
        beyond = self._there(self.bound)
        if beyond != FALSE and not self.hold:
            tied = [f"(= (> {self.count} {at}) {self._there(at)})" for at in range(self.bound)]
            return [f"(assert (>= {self.count} 0))", *(f"(assert {tie})" for tie in tied)], False
        present = [self._there(at) for at in range(self.bound)]
        flags = [TRUE_ONE if there == TRUE else f"(ite {there} 1 0)" for there in present]
        kept = [flag for flag, there in zip(flags, present, strict=True) if there != FALSE]
        total = "0" if not kept else kept[0] if len(kept) == 1 else f"(+ {' '.join(kept)})"
        tied = [f"(assert (= {self.count} {total}))"]
        if beyond != FALSE:
            tied.append(f"(assert {negated(beyond)})")
        return tied, beyond != FALSE

    def _words_count(self) -> str:
        """How many words the string has, at most one past the limit when there is one."""
        words, limit = words_count(self.term), self.limit()
        return words if limit < 0 else f"(ite (< {words} {limit + 1}) {words} {limit + 1})"

    def _held(self) -> None:
        """A read that holds the program; the loosened program makes none."""
        if not self.hold:
            raise LoosenedReadError(f"a loosened program reads no held piece of {self.count}")

    def read(self, position: Lin, kind: str, least: Least) -> SplitRead:
        """The piece at ``position``, and when it is there; whether the read holds the program,
        a choice by the bound or the input's count, or an rsplit's restriction; and whether it
        puts the piece where the input's own few pieces put it, which a later ask may choose
        among every count instead."""
        if kind != "str":
            return SplitRead(Read(None, FALSE), False, False)
        restricted = self.restriction() != TRUE
        if restricted:
            self._held()
        number = position.number()
        if number is not None:
            there = both(self._there(number), self.restriction())
            return SplitRead(Read(self.piece(number), there), restricted, False)
        back = self._from_the_end(position)
        if back is None:
            return SplitRead(self._chosen(position, least), True, False)
        walked = right_piece(self.term, self.head, self.operands, back)
        if walked is not None:
            return SplitRead(Read(walked, self._there(back)), restricted, False)
        if self._at_input_count(back):
            return SplitRead(self._held_back(back), True, self._few())
        return SplitRead(self._counted_back(back), True, False)

    def _from_the_end(self, position: Lin) -> int | None:
        """How far from the last piece a position is, 0 the last, when it is the count less a
        number; None for any other position."""
        if position.atoms == ((self.count, 1),) and position.const < 0:
            return -position.const - 1
        return None

    def _at_input_count(self, back: int) -> bool:
        """Whether piece ``back`` from the end is read where the input's own count puts it: on
        an input with that many pieces whose bound is past `MOST_CHOSEN_BACK`, but for one with
        few pieces once that read is unsat (``chosen``)."""
        count = self.input_count
        if count is None or back >= count or self.bound <= MOST_CHOSEN_BACK:
            return False
        return count > MOST_CHOSEN_BACK or not self.back_among_counts

    def _few(self) -> bool:
        """Whether the bound is one the choice among every count answers within, which also
        makes the input's pieces few: the bound is two past the input's count."""
        return self.bound <= MOST_CHOSEN_BOUND

    def _held_back(self, back: int) -> Read:
        """Piece ``back`` from the end where the string has as many pieces as the input's: the
        piece from the start that puts there, and that count. A path that needs another count
        is asked loosened."""
        self._held()
        count = self.input_count
        assert count is not None
        exact = both(self.past(count - 1), negated(self.past(count)))
        return Read(self.piece(count - 1 - back), both(exact, self.restriction()))

    def _counted_back(self, back: int) -> Read:
        """Piece ``back`` from the end as the piece from the start it is for each count below
        the bound, chosen by which piece is the last there."""
        self._held()
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
        self._held()
        branches = [(f"(= {position.text()} {at})", self.piece(at)) for at in range(self.bound)]
        value = nested(branches[:-1], branches[-1][1])
        return Read(value, both(compare(position, Lin(self.bound), least), self.restriction()))


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
        # whether a read from the end put its piece where the input's own few pieces put it
        self.fixed_few = False
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
            for split, start in _measured(expression):
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
        listed = SplitList(term, str(head), plain, count, bound, self.hold, held, choose)
        self.lists[listed.count] = listed
        self.parts[id(node)] = listed.count
        self.counts[listed.count] = listed.past
        return listed

    def read(self, listed: SplitList, position: Lin, kind: str, least: Least) -> Read:
        """A split's piece at ``position``, noting whether the read holds the program."""
        read = listed.read(position, kind, least)
        if read.held:
            self.bounds.add(listed.count)
        self.fixed_few |= read.fixes_a_few
        return read.found

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
            tie, held = listed.tie()
            if held:
                self.bounds.add(count)
                self.refuted |= least.get(count, 0) > listed.bound
            declared.append(f"(declare-const {count} Int)")
            ties += tie
            pending += [other for other in self.lists if other in "\n".join(tie)]
        return declared, ties


def _measured(expression: list[Expression]) -> list[tuple[list[object], int]]:
    """The splits whose list, or a list built from it, a fork compares the length of,
    ``[op, ["len", parts], n]`` either way round, each with the pieces the slices it is cut by
    leave out from its start: ``len(parts[2:]) > 3`` needs six pieces. A string's, another
    list's or another split's length says nothing of how many pieces a split has."""
    return [
        (split, _start(part[1]))
        for part in expression[1:]
        if isinstance(part, list) and part[:1] == ["len"]
        for split in splits_built_from(part[1])
    ]


def _start(form: Expression) -> int:
    """The pieces the slices a list is cut by leave out from its start, each start a plain
    number past 0."""
    left = 0
    while isinstance(form, list) and form[:1] == ["[:]"]:
        start = form[2] if len(form) > 2 else None
        left += start if type(start) is int and start > 0 else 0
        form = form[1]
    return left
