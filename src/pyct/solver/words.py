"""The edges of the words a split by whitespace finds, for a split built by steps.

Core builds ``split()`` and ``rsplit()`` of a string the solver cannot work
out one word at a time (``core/str_steps.py``), each step a position:

- ``["nextword", s, i]``: the first character at or past i that is not
  whitespace, -1 where none is;
- ``["wordend", s, i]``: the first whitespace at or past i, or the length;
- ``["lastword", s, j]``: the last character before j, the length where j
  is missing, that is not whitespace, -1 where none is;
- ``["wordstart", s, j]``: one past the last whitespace before j, or 0.

Whitespace is every character Python's ``isspace`` takes (`splits.WORD_SPACE`),
so each is exact on every character cvc5 holds. Each is cvc5's
``str.indexof_re`` over one class of characters; the last ones search the
string reversed whole, from the place that stands for j. A missing next word,
and a missing last word from the end, is written as the rest being blank. A
position arrives as a plain int of 0 or more or as an Int term; core writes no
other.
"""

from pyct.solver.splits import NOT_SPACE, SPACE_CLASS
from pyct.solver.strings import length

# the name a form binds: what a search found
_FOUND = "w!found"


def _at(position: int | str | None) -> str:
    """A position as SMT-LIB writes it: a plain int of 0 or more, or an Int term."""
    if position is None or (isinstance(position, int) and position < 0):
        raise ValueError(f"pyct cannot render a word's edge from {position}: core writes 0 or more")
    return str(position)


def _blank(part: str) -> str:
    """Whether a string term holds whitespace alone, or nothing."""
    return f"(str.in_re {part} (re.* {SPACE_CLASS}))"


def next_word(term: str, at: int | str | None) -> str:
    """``s.nextword(i)``: where the first character at or past i that is not whitespace is.

    The -1 is written as the rest being blank: beside a search for a character the string
    holds, cvc5 answered that membership at once where the search's own -1 ran to its limit.
    """
    start = _at(at)
    rest = f"(str.substr {term} {start} (- {length(term)} {start}))"
    return f"(ite {_blank(rest)} (- 1) (str.indexof_re {term} {NOT_SPACE} {start}))"


def word_end(term: str, at: int | str | None) -> str:
    """``s.wordend(i)``: where the first whitespace at or past i is, or the length."""
    found = f"(str.indexof_re {term} {SPACE_CLASS} {_at(at)})"
    return f"(let (({_FOUND} {found})) (ite (= {_FOUND} (- 1)) {length(term)} {_FOUND}))"


def _back(term: str, end: int | str | None, regex: str) -> str:
    """Where the first character of a class is in the reversed string from the place that
    stands for ``end``, or -1: the last one before ``end`` in the string, counted from its end.
    The string is reversed whole, the same term at every step, so cvc5 reads one reversal."""
    start = "0" if end is None else f"(- {length(term)} {_at(end)})"
    return f"(str.indexof_re (str.rev {term}) {regex} {start})"


def last_word(term: str, end: int | str | None = None) -> str:
    """``s.lastword(j)``: where the last character before j that is not whitespace is, or -1.

    From the end of the string, the first step, the -1 is the string being blank, as
    `next_word` writes it: an unsat flip there, a blank string that holds a mark, ran to the
    limit by the search's own -1 and answered in 0.01 s so. Before a word, each later step, it
    is the search's own -1, over the one reversal: a blank part beside each prefix reversed
    apart ran three words from the right to the limit, where this answered in 0.4 s.
    """
    found = _back(term, end, NOT_SPACE)
    if end is None:
        return f"(ite {_blank(term)} (- 1) (- (- {length(term)} 1) {found}))"
    at = f"(- (- {length(term)} 1) {_FOUND})"
    return f"(let (({_FOUND} {found})) (ite (= {_FOUND} (- 1)) (- 1) {at}))"


def word_start(term: str, end: int | str | None) -> str:
    """``s.wordstart(j)``: one past the last whitespace before j, or 0."""
    found = _back(term, end, SPACE_CLASS)
    at = f"(- {length(term)} {_FOUND})"
    return f"(let (({_FOUND} {found})) (ite (= {_FOUND} (- 1)) 0 {at}))"


# each edge by its head, as `heads.FORMS` reads them on a str
WORD_EDGES = {
    "nextword": next_word,
    "wordend": word_end,
    "lastword": last_word,
    "wordstart": word_start,
}
