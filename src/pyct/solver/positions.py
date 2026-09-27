"""Python's positions into a string in SMT-LIB: an index or a slice bound that may be tracked, a
slice with a step of 1 or -1, a search from a start to an end, a tuple of prefixes or
suffixes, and a replace with a count.

A position arrives as a plain int, as the Int term of a tracked one, or as
None where Python's is missing, so a form sees a plain position's sign and
writes a tracked one's in the term. Each form reads a position as Python
does: a negative one counts back from the end, and a slice or a search
clamps it to the string. An index, or a slice without a step, with only
plain positions, and a search or a replace given no position or count, is
the form strings.py writes.

A search from a position looks in the part of the string between its start
and its end, adjusted as CPython's ``ADJUST_INDICES`` adjusts them, and
finds nothing where the end falls before the start, an empty substring
included: ``"abc".find("", 4)`` is -1. `find` is cvc5's own ``str.indexof``
from the start in the string cut at the end; the others read the part as a
string of its own. A step of -1 runs from the start down to the stop, each
clamped as CPython's ``PySlice_AdjustIndices`` clamps a negative step, and
is the part between them reversed.

A form names a term it writes more than once in a ``let``, each name
holding ``!``, which no Python name does; decision
string-positions-adjusted-in-the-term.
"""

from collections.abc import Callable

from pyct.solver import strings
from pyct.solver.strings import length

# a plain position, an Int term, or a missing one
type Position = int | str | None

# what a search looks for: a String term, or a tuple of them from startswith or endswith
type Needle = str | tuple[str, ...]

# the names a form binds: where a search starts, the part it looks in, what it found, and where
# a backward slice's part starts
_START = "start!"
_PART = "part!"
_FOUND = "found!"
_LOW = "low!"


def _number(position: int) -> str:
    """A plain int as SMT-LIB writes it: a negative one is a subtraction."""
    return str(position) if position >= 0 else f"(- {-position})"


def _from_end(term: str, position: int | str, shift: int) -> str:
    """A position counted back from the end, plus ``shift``: ``position + len(s) + shift``."""
    written = _number(position) if isinstance(position, int) else position
    return f"(+ {written} {length(term)}{f' {shift}' if shift else ''})"


def _ahead(position: str, shift: int) -> str:
    """A tracked position of zero or more, plus ``shift``."""
    return f"(+ {position} {shift})" if shift else position


def _counted(term: str, position: int | str, shift: int = 0) -> str:
    """A position counted from the start, plus ``shift``: a negative one counts back from the
    end. Nothing clamps it."""
    if isinstance(position, int):
        return _number(position + shift) if position >= 0 else _from_end(term, position, shift)
    back = _from_end(term, position, shift)
    return f"(ite (< {position} 0) {back} {_ahead(position, shift)})"


def _clamped(term: str, position: int | str, shift: int = 0) -> str:
    """`_counted`, and 0 where a negative position counts back past the beginning."""
    if isinstance(position, int) and position >= 0:
        return _number(position + shift)
    back = _from_end(term, position, shift)
    clamped = f"(ite (< {back} 0) 0 {back})"
    if isinstance(position, int):
        return clamped
    return f"(ite (< {position} 0) {clamped} {_ahead(position, shift)})"


def _let(name: str, value: str, body: str) -> str:
    return f"(let (({name} {value})) {body})"


def character(term: str, index: Position) -> str:
    """``s[i]``: the character at i, a negative i counted back from the end.

    It answers only past the forks that say i is in range, so no clamp is
    needed wherever the term is read.
    """
    if isinstance(index, int):
        return strings.character(term, index)
    if index is None:
        raise ValueError("pyct cannot render an index that is missing: core writes one")
    return f"(str.at {term} {_counted(term, index)})"


def sliced(term: str, start: Position, stop: Position, step: Position = None) -> str:
    """``s[start:stop]``, or ``s[start:stop:step]`` with a step of 1 or -1, each bound clamped to
    the string as Python clamps it.

    Forward, a start that counts back past the beginning is 0, and
    ``str.substr`` gives the empty string for a start past the end or a
    length below one, and stops at the end. Backward, the part runs from
    just past the stop up to and through the start, each counted from the
    end and clamped as the forward bounds are, and is reversed.
    """
    if step == -1:
        return _backward(term, start, stop)
    if step not in (None, 1):
        raise ValueError(f"pyct cannot render a slice with a step of {step}: core writes 1 or -1")
    if not isinstance(start, str) and not isinstance(stop, str):
        return strings.sliced(term, start, stop)
    low = "0" if start is None else _clamped(term, start)
    high = length(term) if stop is None else _counted(term, stop)
    return _let(_LOW, low, f"(str.substr {term} {_LOW} (- {high} {_LOW}))")


def _backward(term: str, start: Position, stop: Position) -> str:
    """``s[start:stop:-1]``: the characters from the start down to just past the stop."""
    low = "0" if stop is None else _clamped(term, stop, 1)
    high = length(term) if start is None else _counted(term, start, 1)
    return _let(_LOW, low, f"(str.rev (str.substr {term} {_LOW} (- {high} {_LOW})))")


def _in_part(
    term: str, start: Position, end: Position, read: Callable[[str], str], missed: str
) -> str:
    """What ``read`` makes of the part of the string a search from start to end looks in.

    Where the end, clamped to the string, falls before the start, the search
    finds nothing and the answer is ``missed``. Without a start or an end,
    the part is the whole string.
    """
    if start is None and end is None:
        return read(term)
    stop = length(term) if end is None else _clamped(term, end)
    part = f"(str.substr {term} {_START} (- {stop} {_START}))"
    looks = f"(and (<= {_START} {length(term)}) (<= {_START} {stop}))"
    first = "0" if start is None else _clamped(term, start)
    return _let(_START, first, f"(ite {looks} {_let(_PART, part, read(_PART))} {missed})")


def first_index(term: str, sub: str, start: Position = None, end: Position = None) -> str:
    """``s.find(sub, start, end)``: where sub first starts from start on, ending by end, or -1.

    cvc5's ``str.indexof`` from the start is -1 for a start past the end of
    what it reads, so the empty substring past the end is not found.
    """
    if start is None and end is None:
        return strings.first_index(term, sub)
    read = term if end is None else f"(str.substr {term} 0 {_clamped(term, end)})"
    first = "0" if start is None else _clamped(term, start)
    return f"(str.indexof {read} {sub} {first})"


def last_index(term: str, sub: str, start: Position = None, end: Position = None) -> str:
    """``s.rfind(sub, start, end)``: where sub last starts in the part, counted from the start
    of s, or -1."""

    def read(part: str) -> str:
        found = f"(ite (= {_FOUND} (- 1)) (- 1) (+ {_START} {_FOUND}))"
        return _let(_FOUND, strings.last_index(part, sub), found)

    if start is None and end is None:
        return strings.last_index(term, sub)
    return _in_part(term, start, end, read, "(- 1)")


def occurrences(term: str, sub: str, start: Position = None, end: Position = None) -> str:
    """``s.count(sub, start, end)``: how many times sub occurs in the part."""
    return _in_part(term, start, end, lambda part: strings.occurrences(part, sub), "0")


def starts_with(term: str, prefix: Needle, start: Position = None, end: Position = None) -> str:
    """``s.startswith(prefix, start, end)``: whether the part starts with the prefix, or with any
    prefix of a tuple."""
    return _in_part(term, start, end, lambda part: _any(strings.starts_with, part, prefix), "false")


def ends_with(term: str, suffix: Needle, start: Position = None, end: Position = None) -> str:
    """``s.endswith(suffix, start, end)``: whether the part ends with the suffix, or with any
    suffix of a tuple."""
    return _in_part(term, start, end, lambda part: _any(strings.ends_with, part, suffix), "false")


def _any(test: Callable[[str, str], str], part: str, needle: Needle) -> str:
    """The test on the part for one needle, or for any needle of a tuple."""
    if isinstance(needle, str):
        return test(part, needle)
    tests = [test(part, item) for item in needle]
    return tests[0] if len(tests) == 1 else f"(or {' '.join(tests)})"


def replaced(term: str, old: str, new: str, count: Position = None) -> str:
    """``s.replace(old, new, count)``: every old turned into new with no count or a negative one,
    the first alone with a count of 1, and none with 0.

    cvc5's ``str.replace`` is Python's replace with a count of 1 for any old
    string: an empty one puts new in front, as Python's does. Every old is
    ``str.replace_all``, which core hands on only for an old string of at
    least one character.
    """
    if count is None or (isinstance(count, int) and count < 0):
        return strings.replaced(term, old, new)
    if count == 1:
        return f"(str.replace {term} {old} {new})"
    if count == 0:
        return term
    raise ValueError(f"pyct cannot render a replace with a count of {count}: core writes 1 or less")
