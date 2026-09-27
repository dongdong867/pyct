"""Python's case changes, strips and paddings in SMT-LIB.

Each is the term for the str Python builds, exact for ASCII. cvc5's
``str.to_upper`` and ``str.to_lower`` change the ASCII letters and leave
every other character as it is, where Python also changes letters past
ASCII, ``é`` to ``É``, and may change the length, ``ß`` to ``SS``; a
character past ASCII has no case here, as it has none in the character
checks (see `checks`).

``title`` and ``swapcase`` are in `recased`.

A padding takes its width, and a strip or a padding its characters, as the
plain values core wrote, so the padding is cut from a literal as long as the
width.
"""

from collections.abc import Callable, Mapping

from pyct.solver.checks import SPACE, Ranges, of, one_of, outside
from pyct.solver.strings import decode, encode, length


def _capitalized(term: str) -> str:
    """``s.capitalize()``: the first character uppercase and the rest lowercase."""
    first = f"(str.to_upper (str.substr {term} 0 1))"
    rest = f"(str.to_lower (str.substr {term} 1 (- {length(term)} 1)))"
    return f"(str.++ {first} {rest})"


def _kept(characters: str | None) -> str:
    """One character a strip keeps: any but whitespace, or any but the characters given.

    The characters arrive as the literal core wrote.
    """
    stripped: Ranges = SPACE if characters is None else of(decode(characters))
    return one_of(outside(stripped))


def _first_kept(term: str, characters: str | None) -> str:
    """Where the first character a strip keeps is in the term, or -1."""
    return f"(str.indexof_re {term} {_kept(characters)} 0)"


def _last_kept_back(term: str, characters: str | None) -> str:
    """How far back from the end the last character a strip keeps is, or -1.

    It is where that character first is in the reversed term.
    """
    return f"(str.indexof_re (str.rev {term}) {_kept(characters)} 0)"


def left_stripped(term: str, characters: str | None = None) -> str:
    """``s.lstrip(chars)``: s from its first character not stripped, or empty."""
    start = _first_kept(term, characters)
    rest = f"(str.substr {term} {start} (- {length(term)} {start}))"
    return f'(ite (= {start} (- 1)) "" {rest})'


def right_stripped(term: str, characters: str | None = None) -> str:
    """``s.rstrip(chars)``: s up to its last character not stripped, or empty."""
    back = _last_kept_back(term, characters)
    return f'(ite (= {back} (- 1)) "" (str.substr {term} 0 (- {length(term)} {back})))'


def stripped(term: str, characters: str | None = None) -> str:
    """``s.strip(chars)``: s from its first character not stripped to its last, or empty.

    Both ends are there together: a string with a character to keep has a
    first one and a last one.
    """
    start = _first_kept(term, characters)
    back = _last_kept_back(term, characters)
    kept = f"(- (- {length(term)} {back}) {start})"
    return f'(ite (= {start} (- 1)) "" (str.substr {term} {start} {kept}))'


def _fill(width: int, fill: str) -> str:
    """As much fill as a padding to ``width`` could need: ``width`` of it, as a literal."""
    return encode(fill * max(width, 0))


def _short_by(term: str, width: int, fill: str) -> str:
    """The fill a padding adds: as many characters as the term is short of the width.

    ``str.substr`` gives the empty string for a length of zero or less, so a
    term as long as the width or longer takes none.
    """
    return f"(str.substr {_fill(width, fill)} 0 (- {width} {length(term)}))"


def left_justified(term: str, width: int, fill: str = " ") -> str:
    """``s.ljust(width, fill)``: s, then fill up to the width."""
    return f"(str.++ {term} {_short_by(term, width, fill)})"


def right_justified(term: str, width: int, fill: str = " ") -> str:
    """``s.rjust(width, fill)``: fill up to the width, then s."""
    return f"(str.++ {_short_by(term, width, fill)} {term})"


def centered(term: str, width: int, fill: str = " ") -> str:
    """``s.center(width, fill)``: s with fill on both sides up to the width.

    Python puts half the margin on the left, rounded down, and one more
    when both the margin and the width are odd; the rest goes on the right.
    The width is a plain int, so whether it is odd is known here.
    """
    margin = f"(- {width} {length(term)})"
    odd = f" (mod {margin} 2)" if width % 2 else " 0"
    left = f"(+ (div {margin} 2){odd})"
    fill_text = _fill(width, fill)
    padded = (
        f"(str.++ (str.substr {fill_text} 0 {left}) {term}"
        f" (str.substr {fill_text} 0 (- {margin} {left})))"
    )
    return f"(ite (<= {margin} 0) {term} {padded})"


def zero_filled(term: str, width: int) -> str:
    """``s.zfill(width)``: zeros up to the width, after a leading sign if s has one."""
    zeros = _short_by(term, width, "0")
    rest = f"(str.substr {term} 1 (- {length(term)} 1))"
    signed = f'(or (str.prefixof "+" {term}) (str.prefixof "-" {term}))'
    padded = f"(ite {signed} (str.++ (str.at {term} 0) {zeros} {rest}) (str.++ {zeros} {term}))"
    return f"(ite (>= {length(term)} {width}) {term} {padded})"


# the case changes and strips, each taking its operands rendered, the characters a strip takes
# as a literal. casefold is lower for ASCII
CASES: Mapping[str, Callable[..., str]] = {
    "upper": lambda term: f"(str.to_upper {term})",
    "lower": lambda term: f"(str.to_lower {term})",
    "casefold": lambda term: f"(str.to_lower {term})",
    "capitalize": _capitalized,
    "strip": stripped,
    "lstrip": left_stripped,
    "rstrip": right_stripped,
}

# the paddings, each taking the string rendered and its width and fill as the plain values
PADDINGS: Mapping[str, Callable[..., str]] = {
    "zfill": zero_filled,
    "center": centered,
    "ljust": left_justified,
    "rjust": right_justified,
}
