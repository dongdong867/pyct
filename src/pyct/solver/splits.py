"""The pieces of a split string in SMT-LIB: the term for each piece, and when it is there.

Python hands the target a list, or a tuple for ``partition``, and the target
takes its pieces out by position. The list has no term of its own: each
piece is ``["[]", ["split", s, sep], k]``, and its term is the string
between the separators Python found around it. A piece is only there when
the string has enough separators, and a piece the target took is there on
the path, so each form also writes that condition, which render asserts
(see `Piece`).

A piece is found by walking the string from the start, one separator at a
time, each step a ``let`` that names where the last one was. ``rsplit``
walks the reversed string the same way. Each form takes the string
rendered, then the plain operands core wrote after it, and the position.
Exact for ASCII. Past ASCII, ``splitlines`` breaks lines where Python does,
and a split on whitespace splits where Python does too (`WORD_SPACE`), though
``isspace`` here reads only ASCII whitespace (see `checks`).
"""

from collections.abc import Callable, Mapping

from pyct.core.str_splits import LONGEST_WALK, overlaps_itself
from pyct.solver.checks import SPACE, Ranges, one_of, outside
from pyct.solver.strings import encode, length

# a piece: its term, and the condition that the string has it
type Piece = tuple[str, str]

# what splitlines ends a line at: \n, \v, \f, \r, the separators \x1c to \x1e, and past ASCII
# the next line, the line separator and the paragraph separator; \r\n is one break
LINE_BREAKS: Ranges = ((0x0A, 0x0D), (0x1C, 0x1E), (0x85, 0x85), (0x2028, 0x2029))

# what split() takes as whitespace: what isspace takes in ASCII, and past it every character
# Python calls whitespace, so a split on whitespace is exact for every character cvc5 holds
WORD_SPACE: Ranges = (
    *SPACE,
    (0x85, 0x85),
    (0xA0, 0xA0),
    (0x1680, 0x1680),
    (0x2000, 0x200A),
    (0x2028, 0x2029),
    (0x202F, 0x202F),
    (0x205F, 0x205F),
    (0x3000, 0x3000),
)

# the two classes a split on whitespace reads, each a regular expression named once in the
# program that reads it, so a walk of many words holds each name rather than its long union
_SPACE, _NOT_SPACE = "re!space", "re!other"
_NAMED: Mapping[str, str] = {
    _SPACE: one_of(WORD_SPACE),
    _NOT_SPACE: one_of(outside(WORD_SPACE)),
}


def named_classes(text: str) -> list[str]:
    """The definition of each class of characters the program's text names."""
    return [
        f"(define-fun {name} () RegLan {regex})" for name, regex in _NAMED.items() if name in text
    ]


_BREAK = one_of(LINE_BREAKS)


def _let(bindings: list[tuple[str, str]], body: str) -> str:
    """The body with each name bound to its term, in order, so a term reads the names before it.

    Each name holds ``!``, which no Python name does, and a name is only
    read inside its own ``let``.
    """
    opened = "".join(f"(let (({name} {term})) " for name, term in bindings)
    return f"{opened}{body}{')' * len(bindings)}"


def _all(conditions: list[str]) -> str:
    """Every condition holds. None is ``true``, one is itself."""
    if not conditions:
        return "true"
    return conditions[0] if len(conditions) == 1 else f"(and {' '.join(conditions)})"


def _rest(term: str, start: str) -> str:
    """The term from ``start`` to its end."""
    return f"(str.substr {term} {start} (- {length(term)} {start}))"


def _between(term: str, start: str, stop: str, end: str | None = None) -> str:
    """The term from ``start`` up to ``end``, or to its end where ``stop`` is -1.

    ``end`` is ``stop`` unless it says otherwise.
    """
    cut = f"(str.substr {term} {start} (- {stop if end is None else end} {start}))"
    return f"(ite (= {stop} (- 1)) {_rest(term, start)} {cut})"


def _past(at: int, width: str) -> str:
    """Where the look for separator ``at`` starts: 0, or just past the one before it."""
    return "0" if at == 0 else f"(+ h!{at - 1} {width})"


def _hits(term: str, separator: str, count: int) -> list[tuple[str, str]]:
    """Where each of the first ``count`` separators starts, ``h!j``, each past the one before."""
    written = encode(separator)
    width = str(len(separator))
    return [
        (f"h!{at}", f"(str.indexof {term} {written} {_past(at, width)})") for at in range(count)
    ]


def parted(term: str, separator: str, limit: int, index: int) -> Piece:
    """Piece ``index`` of ``s.split(sep, maxsplit)``: between two separators, or to the end.

    The last piece a limit allows runs to the end of the string. The piece
    is there when every separator before it was found.
    """
    start = _past(index, str(len(separator)))
    last = 0 <= limit == index
    hits = _hits(term, separator, index if last else index + 1)
    piece = _rest(term, start) if last else _between(term, start, f"h!{index}")
    found = _all([f"(>= h!{at} 0)" for at in range(index)])
    return _let(hits, piece), _let(hits[:index], found)


def _words(term: str, count: int) -> list[tuple[str, str]]:
    """Where each of the first ``count`` words starts, ``a!j``, and where it ends, ``b!j``.

    A word starts at the first character past the last word's end that is
    not whitespace, -1 when there is none, and ends at the next whitespace
    or the end of the string.
    """
    bounds: list[tuple[str, str]] = []
    for at in range(count):
        after = "0" if at == 0 else f"b!{at - 1}"
        bounds.append((f"a!{at}", f"(str.indexof_re {term} {_NOT_SPACE} {after})"))
        space = f"(str.indexof_re {term} {_SPACE} a!{at})"
        bounds.append((f"b!{at}", f"(ite (= {space} (- 1)) {length(term)} {space})"))
    return bounds


def worded(term: str, limit: int, index: int) -> Piece:
    """Piece ``index`` of ``s.split(None, maxsplit)``: a run of characters that are not whitespace.

    The last piece a limit allows runs from its word to the end of the
    string, whitespace and all. The piece is there when its word is.
    """
    bounds = _words(term, index + 1)
    last = 0 <= limit == index
    start, stop = f"a!{index}", f"b!{index}"
    piece = _rest(term, start) if last else f"(str.substr {term} {start} (- {stop} {start}))"
    return _let(bounds, piece), _let(bounds[:-1], f"(>= a!{index} 0)")


def words_count(term: str) -> str:
    """How many words the string has, as one term: a word starts where a character that is
    not whitespace follows whitespace, or the start, and each such pair is removed once."""
    spaced = f'(str.++ " " {term})'
    starts = f'(str.replace_re_all {spaced} (re.++ {_SPACE} {_NOT_SPACE}) "")'
    return f"(div (- (str.len {spaced}) (str.len {starts})) 2)"


def words_past(term: str, index: int) -> str:
    """That the string has more than ``index`` words: whitespace, then ``index`` runs of
    characters that are not whitespace each followed by whitespace, then one more such
    character. One membership, which cvc5 settled at once where the walk of the words ran past
    its limit at five."""
    word = f"(re.++ (re.+ {_NOT_SPACE}) (re.+ {_SPACE}))"
    before = f"((_ re.loop {index} {index}) {word})" if index else ""
    return f"(str.in_re {term} (re.++ (re.* {_SPACE}) {before} {_NOT_SPACE} re.all))"


def split_piece(term: str, operands: tuple[object, ...], index: int) -> Piece:
    """Piece ``index`` of ``s.split()``, ``s.split(sep)`` or ``s.split(sep, maxsplit)``.

    A missing or None separator splits on runs of whitespace.
    """
    separator, limit = _separator_and_limit(operands)
    if separator is None:
        return worded(term, limit, index)
    return parted(term, separator, limit, index)


def _separator_and_limit(operands: tuple[object, ...]) -> tuple[str | None, int]:
    """The separator and the limit a split was called with, -1 for no limit."""
    separator = operands[0] if operands else None
    limit = operands[1] if len(operands) > 1 else -1
    if (separator is not None and not isinstance(separator, str)) or not isinstance(limit, int):
        raise ValueError(f"pyct cannot render a split on {operands}: core writes a str and an int")
    return separator, limit


def right_split_piece(term: str, operands: tuple[object, ...], index: int) -> Piece:
    """Piece ``index`` of ``s.rsplit(sep, maxsplit)``: its pieces are split from the right.

    With no limit, the pieces are the split's own: core hands on no
    separator that overlaps itself, whose separators a split from each end
    finds apart. With a limit, the reversed string is walked once, from its
    start, for as many separators or words as the limit allows: piece ``j``
    from the right is the reversed piece ``j`` of that walk, and piece
    ``index`` from the left is the one ``index`` from the first piece there
    is. Each step names what the one before found, so the term grows with
    the limit, not with its square.
    """
    separator, limit = _separator_and_limit(operands)
    if limit < 0:
        return split_piece(term, operands, index)
    if limit > LONGEST_WALK:
        return _unwalked(term, separator, limit, index)
    walk = _words_back(limit) if separator is None else _separators_back(separator, limit)
    bindings, count, pieces = walk
    # there are at most limit + 1 pieces, so piece index is at most limit - index from the right
    candidates = pieces[: len(pieces) - index]
    opened = "".join(
        f"(ite (= n! {index + at + 1}) {piece} " for at, piece in enumerate(candidates)
    )
    chosen = f'{opened}""{")" * len(candidates)}'
    bound = [("r!", f"(str.rev {term})"), *bindings, ("n!", count)]
    # on a separator there is always a first piece, and asserting so would walk the string again
    there = "true" if separator is not None and index == 0 else _let(bound, f"(> n! {index})")
    return _let(bound, chosen), there


def right_count(term: str, operands: tuple[object, ...]) -> str:
    """How many pieces ``s.rsplit(sep, maxsplit)`` has, by the walk of the reversed string its
    pieces are read from, for a limit it walks, 0 to `LONGEST_WALK`."""
    separator, limit = _separator_and_limit(operands)
    walk = _words_back(limit) if separator is None else _separators_back(separator, limit)
    bindings, count, _ = walk
    return _let([("r!", f"(str.rev {term})"), *bindings], count)


def left_count(term: str, operands: tuple[object, ...]) -> str:
    """How many pieces ``s.split(sep, maxsplit)`` has, for a limit of 0 or more: one walk from
    the start, each separator or word counted once it is found, and none after one is missing.
    """
    separator, limit = _separator_and_limit(operands)
    if separator is None:
        return _sum([f"(ite {words_past(term, at)} 1 0)" for at in range(limit + 1)])
    written, width = encode(separator), len(separator)
    hits = [("h!0", f"(str.indexof {term} {written} 0)")] if limit else []
    for at in range(1, limit):
        look = f"(str.indexof {term} {written} (+ h!{at - 1} {width}))"
        hits.append((f"h!{at}", f"(ite (< h!{at - 1} 0) (- 1) {look})"))
    return _let(hits, _sum(["1", *(f"(ite (>= h!{at} 0) 1 0)" for at in range(limit))]))


def _unwalked(term: str, separator: str | None, limit: int, index: int) -> Piece:
    """Piece ``index`` of an rsplit whose limit is past `LONGEST_WALK`, read as the split's.

    The two agree on a string with no more separators than the limit, or
    fewer words, so the piece also asserts that the string is one: every
    answer is then Python's. A string with more is no answer, so a path that
    needs one is a miss.
    """
    piece, there = split_piece(term, (separator,), index)
    return piece, _all([there, unwalked_bound(term, separator, limit)])


def unwalked_bound(term: str, separator: str | None, limit: int) -> str:
    """That an rsplit whose limit is past `LONGEST_WALK` splits the string as the split with no
    limit does: the string has no more separators than the limit, or fewer words."""
    if separator is None:
        return f"(< {words_count(term)} {limit})"
    # a literal replace, which cvc5 answered at once where the same count as a regular
    # expression ran past its limit
    kept = f'(str.len (str.replace_all {term} {encode(separator)} ""))'
    separators = f"(div (- (str.len {term}) {kept}) {len(separator)})"
    return f"(<= {separators} {limit})"


# a walk of the reversed string: the names it binds, how many pieces the string has, and each
# piece from the right, written with those names
type Walk = tuple[list[tuple[str, str]], str, list[str]]


def _separators_back(separator: str, limit: int) -> Walk:
    """The first ``limit`` separators of the reversed string, ``h!j``, -1 once one is missing."""
    written, width = encode(separator[::-1]), len(separator)
    hits = [("h!0", f"(str.indexof r! {written} 0)")]
    for at in range(1, limit):
        look = f"(str.indexof r! {written} (+ h!{at - 1} {width}))"
        hits.append((f"h!{at}", f"(ite (< h!{at - 1} 0) (- 1) {look})"))
    found = [f"(ite (>= h!{at} 0) 1 0)" for at in range(limit)]
    starts = ["0", *(f"(+ h!{at} {width})" for at in range(limit))]
    stops = [f"(ite (< h!{at} 0) (str.len r!) h!{at})" for at in range(limit)] + ["(str.len r!)"]
    pieces = [_back(start, stop) for start, stop in zip(starts, stops, strict=True)]
    return hits, _sum(["1", *found]), pieces


def _words_back(limit: int) -> Walk:
    """The first ``limit`` + 1 words of the reversed string; the last runs to its end."""
    bounds = _words("r!", limit + 1)
    found = [f"(ite (>= a!{at} 0) 1 0)" for at in range(limit + 1)]
    stops = [f"b!{at}" for at in range(limit)] + ["(str.len r!)"]
    pieces = [_back(f"a!{at}", stop) for at, stop in enumerate(stops)]
    return bounds, _sum(found), pieces


def right_piece(term: str, head: str, operands: tuple[object, ...], back: int) -> str | None:
    """Piece ``back`` of a split counted from the right, 0 the last, where one walk of the
    reversed string finds it; None for a split it does not.

    The walk finds a split's pieces with no limit on whitespace, or on a separator that does
    not overlap itself, and an rsplit's to the limit it walks. A split with a limit keeps the
    rest of the string in its last piece, and one on a separator that overlaps itself finds
    other pieces from the right, so neither is walked from there. An rsplit past
    `LONGEST_WALK` is read as the split with no limit, as its pieces are.
    """
    if head not in ("split", "rsplit"):
        return None
    separator, limit = _separator_and_limit(operands)
    walked = head == "rsplit" and 0 <= limit <= LONGEST_WALK
    # a split with a limit, or an rsplit's piece at its limit or past it, holds the rest
    if (head == "split" and limit >= 0) or 0 <= limit <= back:
        return None
    if not walked and separator is not None and overlaps_itself(separator):
        return None
    steps = limit if walked else back + 1
    walk = _words_back(steps) if separator is None else _separators_back(separator, steps)
    bindings, _, pieces = walk
    return _let([("r!", f"(str.rev {term})"), *bindings], pieces[back])


def _back(start: str, stop: str) -> str:
    """The reversed string from ``start`` up to ``stop``, turned the right way round."""
    return f"(str.rev (str.substr r! {start} (- {stop} {start})))"


def _sum(terms: list[str]) -> str:
    """The terms added up. One is itself."""
    return terms[0] if len(terms) == 1 else f"(+ {' '.join(terms)})"


def partition_piece(term: str, operands: tuple[object, ...], index: int) -> Piece:
    """Piece ``index`` of ``s.partition(sep)``: before the first separator, it, and after.

    When the separator is not there, the string and then two empty strings.
    Every piece is always there.
    """
    (separator,) = operands
    if not isinstance(separator, str):
        raise ValueError(f"pyct cannot render a partition on {separator!r}: core writes a str")
    found = f"(str.indexof {term} {encode(separator)} 0)"
    pieces = (
        f"(str.substr {term} 0 h!0)",
        encode(separator),
        _rest(term, f"(+ h!0 {len(separator)})"),
    )
    missing = (term, '""', '""')
    piece = f"(ite (= h!0 (- 1)) {missing[index]} {pieces[index]})"
    return _let([("h!0", found)], piece), "true"


def _breaks(term: str, count: int) -> list[tuple[str, str]]:
    """Where each of the first ``count`` line breaks starts, ``h!j``, and how long it is, ``w!j``.

    A break is one character, but for a carriage return right before a line
    feed, which is one break of two.
    """
    breaks: list[tuple[str, str]] = []
    for at in range(count):
        past = _past(at, f"w!{at - 1}")
        breaks.append((f"h!{at}", f"(str.indexof_re {term} {_BREAK} {past})"))
        pair = f'(= (str.substr {term} h!{at} 2) "\\u{{d}}\\u{{a}}")'
        breaks.append((f"w!{at}", f"(ite {pair} 2 1)"))
    return breaks


def line_piece(term: str, operands: tuple[object, ...], index: int) -> Piece:
    """Line ``index`` of ``s.splitlines(keepends)``: up to its break, with it when kept.

    A line is there when every break before it was found and the string
    goes on past the last of them: a break at the very end starts no line.
    """
    keep = bool((*operands, False)[0])
    breaks = _breaks(term, index + 1)
    start = _past(index, f"w!{index - 1}")
    end = f"(+ h!{index} w!{index})" if keep else None
    piece = _between(term, start, f"h!{index}", end)
    found = [f"(>= h!{at} 0)" for at in range(index)]
    there = _all([*found, f"(< {start} {length(term)})"])
    return _let(breaks, piece), _let(breaks[: 2 * index], there)


# each split's piece at a position, from the string rendered, the plain operands core wrote
# after it, and the position
SPLITS: Mapping[str, Callable[[str, tuple[object, ...], int], Piece]] = {
    "split": split_piece,
    "rsplit": right_split_piece,
    "partition": partition_piece,
    "splitlines": line_piece,
}
