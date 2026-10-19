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
``str.indexof_re`` over one class of characters, read over the reversed part
before j for the last ones, with a blank part written as a membership. A
position arrives as a plain int of 0 or more or as an Int term; core writes no
other.
"""

from pyct.solver.splits import NOT_SPACE, SPACE_CLASS
from pyct.solver.strings import length

# the names a form binds: what a search found, and the part before a position it searched
_FOUND = "w!found"
_PART = "w!part"


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


def _back(regex: str) -> str:
    """How far back from the end of the part the last character of a class in it is: where the
    first one starts in the part reversed, or -1."""
    return f"(str.indexof_re (str.rev {_PART}) {regex} 0)"


def last_word(term: str, end: int | str | None = None) -> str:
    """``s.lastword(j)``: where the last character before j that is not whitespace is, or -1.

    The -1 is written as the part being blank, as `next_word` writes it; a part that is not
    blank holds such a character, so the search back finds one.
    """
    stop = length(term) if end is None else _at(end)
    body = f"(ite {_blank(_PART)} (- 1) (- (- {stop} 1) {_back(NOT_SPACE)}))"
    return f"(let (({_PART} (str.substr {term} 0 {stop}))) {body})"


def word_start(term: str, end: int | str | None) -> str:
    """``s.wordstart(j)``: one past the last whitespace before j, or 0."""
    stop = _at(end)
    found = f"(ite (= {_FOUND} (- 1)) 0 (- {stop} {_FOUND}))"
    back = f"(let (({_FOUND} {_back(SPACE_CLASS)})) {found})"
    return f"(let (({_PART} (str.substr {term} 0 {stop}))) {back})"


# each edge by its head, as `heads.FORMS` reads them on a str
WORD_EDGES = {
    "nextword": next_word,
    "wordend": word_end,
    "lastword": last_word,
    "wordstart": word_start,
}
