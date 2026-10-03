"""A split's list as cvc5 reads it: how many pieces it holds, and the piece at a position.

``split``, ``rsplit`` and ``splitlines`` hand the target a tracked list whose form is the call
(follow-the-length-of-a-split). No term holds the list. Each piece is the term `splits` writes
for its position, and the list's length is how many pieces the string has, which no term of
SMT-LIB counts at once. So a compare of the length with a plain int, directly or through `+`,
`-` or `*` with one, is written as whether a piece is there: ``len(parts) > 2`` is that piece 2
is there, which `splits` already writes for each form, exact for every string. That holds
wherever the lists write such a compare, a fork or the branch of a read.

A length that meets anything else, a tracked value, another split's length, a slice's clamp,
is the number c*: the input's own count, moved as little as the path's compares with plain
ints need (``read_count``). That is the ask origin/v2 makes, whose length is plain: an answer
there may hold another count, and an unsat says only that no string of c* pieces takes the
path. Decision split-list-tracked-its-count-the-piece-there-or-the-input-s-own.

A piece is read at a number from the start; from the end by a walk of the reversed string
where one reads it (`splits.right_piece`); and otherwise from the end where c* puts it, the
string held to c* pieces. An ask that holds a string so comes back unsat or unknown is asked
once more as origin/v2 asks, the piece read where the input's own count puts it with no count
held (``fixed`` false, see `solver.cvc5`). A position a term writes, a tracked slice bound's
say, is read where the input's own values put it, as origin/v2 reads it.
"""

from __future__ import annotations

from dataclasses import dataclass

from pyct.core.str_splits import LONGEST_WALK
from pyct.solver.list_terms import FALSE, TRUE, Lin, Read, both, negated
from pyct.solver.splits import (
    SPLITS,
    left_count,
    right_count,
    right_piece,
    separators_past,
    split_piece,
    unwalked_bound,
    words_past,
)

# the largest number a compare of a separator split's count with a number is written as the
# walk to that piece, which cvc5 answers fastest beside the pieces a path reads and their int
# conversions; past it, as one membership, since a walk to 1,000 ran past the limit where the
# membership answered in 0.02 s
MOST_WALKED_PAST = 16


@dataclass(frozen=True)
class SplitRead:
    """A read of a split's piece: what it found, and whether it held the string to c* pieces."""

    found: Read
    fixes_the_count: bool = False


@dataclass(frozen=True)
class SplitList:
    """One split's list: the string's term, the method and its plain operands, and the name its
    count goes by.

    ``input_count`` is how many pieces Python makes of the input's own string, where it is
    known; ``read_count`` is c*, that count moved as little as the path's compares with plain
    ints need. With ``fixed`` false, a piece from the end that no walk of the reversed string
    reads is read where the input's own count puts it, with no count held.
    """

    term: str
    head: str
    operands: tuple[object, ...]
    count: str
    input_count: int | None = None
    read_count: int | None = None
    fixed: bool = True

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

    def read(self, position: Lin, kind: str, at_input: int | None) -> SplitRead:
        """The piece at ``position``, and when it is there. ``at_input`` is the position's value
        in the input whose path this is, where it is known, which a position a term writes is
        read at."""
        if kind != "str":
            return SplitRead(Read(None, FALSE))
        number = position.number()
        if number is None:
            back = self._from_the_end(position)
            if back is not None:
                return self._back(back)
            number = at_input
        if number is None:
            return SplitRead(Read(None, FALSE))
        return SplitRead(self.at(number))

    def from_the_end(self, position: Lin) -> bool:
        """Whether a position is the count less a number."""
        return self._from_the_end(position) is not None

    def _from_the_end(self, position: Lin) -> int | None:
        """How far from the last piece a position is, 0 the last, when it is the count less a
        number; None for any other position."""
        if position.atoms == ((self.count, 1),) and position.const < 0:
            return -position.const - 1
        return None

    def at(self, index: int) -> Read:
        """Piece ``index`` from the start, and that it is there; none before the first."""
        if index < 0:
            return Read(None, FALSE)
        return Read(self.piece(index), both(self._there(index), self.restriction()))

    def held_at(self, index: int) -> SplitRead:
        """Piece ``index`` from the start on a string held to c* pieces; none past them."""
        count = self.read_count
        assert count is not None
        if not 0 <= index < count:
            return SplitRead(Read(None, FALSE))
        # by the walks the piece is read with: past 16 pieces, a count by membership beside
        # the walk ran past the limit where these answered in 1.4 to 2.9 s
        exact = both(self._there(count - 1), negated(self._there(count)))
        found = Read(self.piece(index), both(exact, self.restriction()))
        return SplitRead(found, fixes_the_count=True)

    def _back(self, back: int) -> SplitRead:
        """Piece ``back`` from the end: by a walk of the reversed string where one reads it,
        else where c* puts it with the string held to c* pieces, or, with ``fixed`` false or
        no c*, where the input's own count puts it."""
        walked = right_piece(self.term, self.head, self.operands, back)
        if walked is not None:
            return SplitRead(Read(walked, both(self._there(back), self.restriction())))
        count = self.read_count
        if self.fixed and count is not None and back < count:
            return self.held_at(count - 1 - back)
        own = self.input_count
        if own is None:
            return SplitRead(Read(None, FALSE))
        return SplitRead(self.at(own - 1 - back))
