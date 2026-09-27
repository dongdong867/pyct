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
and a split on whitespace reads only ASCII whitespace, as ``isspace`` does
here (see `checks`).
"""

from collections.abc import Callable, Mapping

from pyct.solver.checks import SPACE, Ranges, one_of, outside
from pyct.solver.strings import encode, length

# a piece: its term, and the condition that the string has it
type Piece = tuple[str, str]

# what splitlines ends a line at: \n, \v, \f, \r, the separators \x1c to \x1e, and past ASCII
# the next line, the line separator and the paragraph separator; \r\n is one break
LINE_BREAKS: Ranges = ((0x0A, 0x0D), (0x1C, 0x1E), (0x85, 0x85), (0x2028, 0x2029))

_SPACE = one_of(SPACE)
_NOT_SPACE = one_of(outside(SPACE))
_BREAK = one_of(LINE_BREAKS)


def _let(bindings: list[tuple[str, str]], body: str) -> str:
    """The body with each name bound to its term, in order, so a term reads the names before it.

    Each name holds ``!``, which no Python name does, and a name is only
    read inside its own ``let``.
    """
    for name, term in reversed(bindings):
        body = f"(let (({name} {term})) {body})"
    return body


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
    finds apart. With a limit, piece ``j`` from the right is piece ``j`` of the
    reversed string split by the reversed separator, reversed; piece
    ``index`` from the left is the one as far from the last piece there is.
    """
    separator, limit = _separator_and_limit(operands)
    if limit < 0:
        return split_piece(term, operands, index)
    back = [_mirrored("r!0", separator, limit, at) for at in range(limit + 1)]
    piece = back[0][0]
    for last in range(index + 1, limit + 1):
        piece = f"(ite {back[last][1]} {back[last - index][0]} {piece})"
    bound = [("r!0", f"(str.rev {term})")]
    there = back[index][1]
    return _let(bound, piece), there if there == "true" else _let(bound, there)


def _mirrored(reversed_term: str, separator: str | None, limit: int, at: int) -> Piece:
    """Piece ``at`` from the right of an rsplit, from the reversed string's split."""
    if separator is None:
        piece, there = worded(reversed_term, limit, at)
    else:
        piece, there = parted(reversed_term, separator[::-1], limit, at)
    return f"(str.rev {piece})", there


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
