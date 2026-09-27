"""The characters a path reads of a string at fixed positions, written as its first letters.

A walk over a string reads ``s[0]``, ``s[1]``, and on to its last pass, and
cvc5 answers a path of many ``(str.at s i)`` slowly: forty positions run past
its time limit. A string read densely at fixed positions from zero is written
instead as its first letters and the rest, ``s = c0 ++ c1 ++ … ++ cm ++ rest``,
and the same path is answered in hundredths of a second, a path over hundreds
of positions inside the limit.

Each letter ``ci`` is exactly ``(str.at s i)``: one character where s is
longer than i, and the empty string where it is not, so the program asks
the same question either way. Where the path itself says s is longer than
i, as a walk's pass fork or an index's long-enough fork does, the letter is
held to one character outright, which cvc5 reads fastest.
"""

from collections.abc import Callable, Hashable, Iterable

from pyct.core.branch import Branch, Expression
from pyct.solver.dag import Node

# what tells one string from another here: a leaf's name, or the id of the part that writes it
type Key = Hashable

# how the program finds a string's key: None for a part that is no string
type Keyed = Callable[[Expression], Key | None]

# the head of an index, and the heads of a fork that says a string is at least so long:
# `len(s) > i` holds s[i], and `len(s) >= i` holds s[i - 1]
_INDEX = "[]"
_LONGER: dict[str, int] = {">": 1, ">=": 0}


def furthest_reads(order: Iterable[Node], key: Keyed) -> dict[Key, int]:
    """For each string the path reads densely at fixed positions from zero, the furthest letter
    to spell.

    The letters run from position 0 to the furthest read position at which
    at least half the letters so far are read, so a walk, which reads every
    position, spells them all, and the program never holds more than twice
    as many letters as reads: `s[0]`, `s[1]` and `s[20000]` spell two
    letters, not twenty thousand, and `s[0]` and `s[20000]` spell none. A
    read past the letters reads the rest (see `past_the_letters`). A string
    with fewer than two reads in its letters gains nothing from them, and a
    path that cuts a string down pass by pass reads each piece once: spelled
    out, each piece would be one more equation for cvc5 to hold.
    """
    read: dict[Key, set[int]] = {}
    for node in order:
        at = fixed_position(node)
        if at is not None and (string := key(node[1])) is not None:
            read.setdefault(string, set()).add(at)
    dense = {string: _dense_end(sorted(positions)) for string, positions in read.items()}
    return {string: end for string, end in dense.items() if end is not None}


def _dense_end(positions: list[int]) -> int | None:
    """The furthest position with at least half the letters up to it read, when two or more
    reads lie within; else None."""
    ends = [at for count, at in enumerate(positions, 1) if 2 * count >= at + 1 and count > 1]
    return ends[-1] if ends else None


def fixed_position(node: Node) -> int | None:
    """The position an index reads, when it is a plain int of zero or more; else None."""
    if len(node) != 3 or node[0] != _INDEX:
        return None
    at = node[2]
    return at if type(at) is int and at >= 0 else None


def held_lengths(prefix: Iterable[Branch], key: Keyed) -> dict[Key, int]:
    """For each string a taken fork holds at least so long, the longest length held."""
    held: dict[Key, int] = {}
    for fork in prefix:
        length = _held_length(fork)
        if length is not None and (string := key(length[0])) is not None:
            held[string] = max(held.get(string, 0), length[1])
    return held


def _held_length(fork: Branch) -> tuple[Expression, int] | None:
    """The string a fork holds at least so long, and that length, or None for any other fork."""
    expression = fork.expression
    if not fork.taken or not isinstance(expression, list) or len(expression) != 3:
        return None
    head, measured, bound = expression
    if head not in _LONGER or type(bound) is not int:
        return None
    if not isinstance(measured, list) or len(measured) != 2 or measured[0] != "len":
        return None
    return measured[1], bound + _LONGER[str(head)]


def spelled(term: str, names: list[str], rest: str, held: int) -> list[str]:
    """The declarations and assertions that write ``term`` as its first letters and the rest.

    ``names`` are the letters in order, from position 0, and ``held`` how
    many of them the path holds there.
    """
    lines = [f"(declare-const {name} String)" for name in [*names, rest]]
    for at, name in enumerate(names):
        there = "1" if at < held else f"(ite (> (str.len {term}) {at}) 1 0)"
        lines.append(f"(assert (= (str.len {name}) {there}))")
    lines.append(f"(assert (= {term} (str.++ {' '.join(names)} {rest})))")
    return lines


def past_the_letters(rest: str, at: int) -> str:
    """A read ``at`` places past a spelled string's letters: that place in the rest.

    It is exactly the string's own character there. Where the string is
    longer than its letters, each letter is one character and the rest is
    what follows them; where it is not, the rest is empty, and so is the
    string past its end.
    """
    return f"(str.at {rest} {at})"


class Spellings:
    """The strings a path spells out, each on its first read, and what each read of one is."""

    def __init__(self, order: Iterable[Node], prefix: Iterable[Branch], key: Keyed) -> None:
        self.furthest = furthest_reads(order, key)
        self.held = held_lengths(prefix, key)
        self.names: dict[Key, list[str]] = {}

    def spells(self, string: Key) -> bool:
        """Whether the path reads this string densely enough to spell it."""
        return string in self.furthest

    def read(self, string: Key, at: int, term: str) -> tuple[str, list[str]]:
        """What a read of ``string`` at ``at`` is, its letter or its place in the rest, and the
        lines to write before it: the spelling, on the string's first read."""
        last = self.furthest[string]
        lines: list[str] = []
        if string not in self.names:
            count = len(self.names)
            self.names[string] = [f"c!{count}!{k}" for k in range(last + 1)] + [f"r!{count}"]
            *letters, rest = self.names[string]
            lines = spelled(term, letters, rest, self.held.get(string, 0))
        names = self.names[string]
        return (names[at] if at <= last else past_the_letters(names[-1], at - last - 1)), lines
