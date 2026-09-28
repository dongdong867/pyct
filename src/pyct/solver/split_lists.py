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

from dataclasses import dataclass

from pyct.core.str_splits import LONGEST_WALK
from pyct.solver.list_terms import FALSE, TRUE, Least, Lin, Read, both, compare, negated, nested
from pyct.solver.splits import (
    SPLITS,
    last_line,
    left_count,
    right_count,
    right_piece,
    separators_past,
    split_piece,
    unwalked_bound,
    words_count,
    words_past,
)
from pyct.solver.strings import encode

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
# the input's own count is unsat. A separator or whitespace split reads at the input's count
# first at any bound, and splitlines where its bound is past this: on cvc5 1.3.4 the last of 8
# lines read there answered in 1.7 s,
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
    input_text: str | None = None
    compared: int = 0
    read_count: int | None = None

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

    def tie(self, read_from_the_end: bool = False) -> tuple[list[str], bool]:
        """What the count is: on whitespace, the words the string has, at most the limit's
        pieces; on a separator whose list the path reads from the end, as one replace term at
        any bound (see `_counted_tie`); otherwise the pieces there below the bound, each by its
        walk, and none at it. Loosened, the count is only past each number below the bound
        where that piece is there. A tie by walks answered where one by memberships ran past the
        limit beside a slice. Says whether it holds the count to the bound."""
        if self._words():
            return [f"(assert (= {self.count} {self._words_count()}))"], False
        if read_from_the_end and self._separated() and self.hold:
            return self._counted_tie()
        beyond = self._there(self.bound)
        if beyond != FALSE and self.hold and self._pinned():
            return self._pinned_tie(), True
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

    def _pinned(self) -> bool:
        """Whether a count tied by walks is held to the input's own count: where the input's
        own pieces, not a number the path compares with, take the bound past
        `MOST_WALKED_PAST`, a tie of that many walks ran past the limit (17 lines, 24 pieces on
        `--`), so the count is read as Python counted the input's string, and a path that needs
        another count is asked loosened."""
        count = self.input_count
        moved = count != self.read_count
        return (
            count is not None and not moved and self.bound == count + BOUND_PAST > MOST_WALKED_PAST
        )

    def _pinned_tie(self) -> list[str]:
        """The count as the input's own, and the string as one with that many pieces: on a
        separator by memberships, which answered 24 pieces on `--` where the walks and a replace
        term ran past the limit; on lines and words as the input's own string, since 17 lines
        counted by their walks or by a replace term ran past the limit, where origin/v2, whose
        length is plain, answers at once."""
        count, text = self.input_count, self.input_text
        assert count is not None and text is not None
        separator = self.operands[0] if self._separated() else None
        if isinstance(separator, str):
            fewer = negated(separators_past(self.term, separator, count))
            exact = both(separators_past(self.term, separator, count - 1), fewer)
        else:
            exact = f"(= {self.term} {encode(text)})"
        return [f"(assert (= {self.count} {count}))", f"(assert {exact})"]

    def _counted_tie(self) -> tuple[list[str], bool]:
        """A separator split's count as one replace term, held to the bound by one membership
        where its limit does not already keep it under the bound: beside a read from the end at
        the input's count, a tie of ten walks ran past the limit where these answered in 0.1 s,
        and at 9 to 16 pieces in 0.4 to 4.7 s. Says whether it holds the count."""
        separator = self.operands[0]
        assert isinstance(separator, str)
        counted = f"(assert (= {self.count} {self._separators_count()}))"
        if 0 <= self.limit() < self.bound:
            return [counted], False
        beyond = separators_past(self.term, separator, self.bound)
        return [counted, f"(assert {negated(beyond)})"], True

    def _separated(self) -> bool:
        """Whether it splits on a separator from the start, or an rsplit that counts as the
        split does past its walk."""
        separated = self.head in ("split", "rsplit") and bool(self.operands)
        return separated and isinstance(self.operands[0], str) and not self._walked()

    def _separators_count(self) -> str:
        """How many pieces it has, as one term: one more than the separators a literal replace
        removes, which are the ones side by side from the start that the split cuts at, at most
        the limit."""
        separator = self.operands[0]
        assert isinstance(separator, str)
        kept = f'(str.len (str.replace_all {self.term} {encode(separator)} ""))'
        found = f"(div (- (str.len {self.term}) {kept}) {len(separator)})"
        limit = self.limit()
        if limit >= 0:
            found = f"(ite (< {found} {limit}) {found} {limit})"
        return f"(+ 1 {found})"

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
        if self.head == "splitlines" and back == 0 and self.compared <= 1:
            # one look from the end, where no fork compares the count with more than 1: beside
            # a count walked to 7 or 10 it ran past the limit where the read at the input's
            # count answered
            walked = last_line(self.term, self.operands)
        if walked is not None:
            return SplitRead(Read(walked, self._there(back)), restricted, False)
        if self._at_input_count(back):
            return SplitRead(self._held_back(back), True, self._few())
        return SplitRead(self._counted_back(back), True, False)

    def from_the_end(self, position: Lin) -> bool:
        """Whether a position is the count less a number."""
        return self._from_the_end(position) is not None

    def _from_the_end(self, position: Lin) -> int | None:
        """How far from the last piece a position is, 0 the last, when it is the count less a
        number; None for any other position."""
        if position.atoms == ((self.count, 1),) and position.const < 0:
            return -position.const - 1
        return None

    def _at_input_count(self, back: int) -> bool:
        """Whether piece ``back`` from the end is read where the input's own count puts it,
        moved as little as the forks on the split's length need (``read_count``): on an input
        with that many pieces, for splitlines where the bound is past `MOST_CHOSEN_BACK`, but
        for an input with few pieces once that read is unsat (``back_among_counts``)."""
        count = self.read_count
        if count is None or back >= count:
            return False
        if self.head == "splitlines" and self.bound <= MOST_CHOSEN_BACK:
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
        count = self.read_count
        assert count is not None
        # by the walks the piece is read with: past 16 pieces, a count by membership beside the
        # walk ran past the limit where these answered in 1.4 to 2.9 s
        exact = both(self._there(count - 1), negated(self._there(count)))
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
