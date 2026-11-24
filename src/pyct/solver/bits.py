"""Python's bit operations on ints in SMT-LIB: `&`, `|`, `^` and `~`, and shifts by a constant.

Python works on an int's infinite two's complement, so each form below holds
for a negative int too. `~x` is `-x - 1`, `x << c` is `x * 2**c`, and `x >> c`
is `x` floored by `2**c`, which SMT-LIB's `div` by a positive number is. An
`&` with a constant is cvc5's `(_ iand k)` on the low `k` bits, `k` the width
of the constant's finite bits, and a negative constant keeps the bits from
`k` up as they are: exact for every int. An `&` of two tracked ints is
`(_ iand 64)` on their low 64 bits, less `2**64` when both are negative,
which is exact while both lie in ``[LOWEST, HIGHEST]``; render holds that
bound on the path (``BOUNDED`` in `solver/heads.py`), and past it the term is
an Int of its own. `|` and `^` are `x + y - (x & y)` and `x + y - 2 * (x & y)`,
which hold for every pair of ints.

Core writes a plain operand as the literal it is, and render writes a literal
int as its numeral, so a constant arrives as ``5`` or ``(- 5)``; a bool
arrives as the int 1 or 0 it is.
"""

import re

from pyct.solver.unencoded import UnencodedError

# the width two tracked ints meet in, and the range each is exact inside
_WIDTH = 64
LOWEST, HIGHEST = -(2 ** (_WIDTH - 1)), 2 ** (_WIDTH - 1) - 1

# an int literal as render writes it
_NUMERAL = re.compile(r"\d+|\(- \d+\)")


def _constant(term: str) -> int | None:
    """The int a literal term is, or None for any other term."""
    if _NUMERAL.fullmatch(term) is None:
        return None
    return -int(term[len("(- ") : -1]) if term.startswith("(") else int(term)


def _with_constant(term: str, mask: int) -> str:
    """``term & mask`` for a constant mask, exact for every int ``term``."""
    width = (~mask if mask < 0 else mask).bit_length()
    if width == 0:
        return term if mask < 0 else "0"
    whole = 2**width
    low = f"(mod {term} {whole})"
    if mask % whole != whole - 1:
        low = f"((_ iand {width}) {low} {mask % whole})"
    return f"(+ {low} (- {term} (mod {term} {whole})))" if mask < 0 else low


def _anded(left: str, right: str) -> tuple[str, str | None]:
    """``left & right``, and the bound it is exact inside, or None where a side is a constant."""
    for term, other in ((left, right), (right, left)):
        mask = _constant(other)
        if mask is not None:
            return _with_constant(term, mask), None
    whole = 2**_WIDTH
    low = f"((_ iand {_WIDTH}) (mod {left} {whole}) (mod {right} {whole}))"
    negative = f"(and (< {left} 0) (< {right} 0))"
    bound = f"(and {_inside(left)} {_inside(right)})"
    return f"(- {low} (ite {negative} {whole} 0))", bound


def _inside(term: str) -> str:
    """Whether an Int term lies in the range two tracked ints are exact inside."""
    return f"(<= (- {-LOWEST}) {term} {HIGHEST})"


def bitwise_and(left: str, right: str, past: str | None = None) -> tuple[str, str | None]:
    """Python's ``&`` on two Int terms, and the bound it is exact inside, if any.

    Given ``past``, the term past the bound is that Int constant, which render
    declares for this term alone, so an unsat holds for whatever Python gives
    there.
    """
    term, bound = _anded(left, right)
    if bound is None or past is None:
        return term, bound
    return f"(ite {bound} {term} {past})", bound


def bitwise_or(left: str, right: str, past: str | None = None) -> tuple[str, str | None]:
    """Python's ``|`` on two Int terms, through their ``&``, and its bound."""
    anded, bound = bitwise_and(left, right, past)
    return f"(- (+ {left} {right}) {anded})", bound


def bitwise_xor(left: str, right: str, past: str | None = None) -> tuple[str, str | None]:
    """Python's ``^`` on two Int terms, through their ``&``, and its bound."""
    anded, bound = bitwise_and(left, right, past)
    return f"(- (+ {left} {right}) (* 2 {anded}))", bound


def inverted(term: str) -> str:
    """Python's ``~`` on an Int term."""
    return f"(- (- {term}) 1)"


def shifted_left(term: str, count: str) -> str:
    """Python's ``<<`` by a constant count on an Int term."""
    return f"(* {term} {2 ** _count(count)})"


def shifted_right(term: str, count: str) -> str:
    """Python's ``>>`` by a constant count on an Int term."""
    return f"(div {term} {2 ** _count(count)})"


def _count(count: str) -> int:
    """A shift's count, which core writes only as a plain int from zero up."""
    number = _constant(count)
    if number is None or number < 0:
        raise UnencodedError(f"pyct cannot render a shift by {count}: only a constant count")
    return number
