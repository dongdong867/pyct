"""Python floats in SMT-LIB: a double literal both ways, and the forms no one operator spells.

A tracked float is an IEEE-754 double in cvc5's floating-point theory, and
every operation render writes rounds to nearest even, as CPython does, so an
answer takes the side it aimed for to the last bit; decision
float-ieee-double-in-cvc5.

A literal is written as the double's own bit pattern, ``(fp #bS #bE #bF)``:
the sign, the eleven exponent bits and the fifty-two fraction bits. No
decimal is rounded on the way, and -0.0, the subnormals, the infinities and
NaN are written like any other double. cvc5 prints a Float64 value in the
same form, so reading one back undoes the step exactly.

``==`` and ``!=`` are IEEE equality, ``fp.eq``, as Python's are. SMT-LIB's
``=`` is sameness instead: on cvc5 1.3.4 it calls NaN equal to itself and
tells -0.0 from 0.0.

``whole`` is ``float.is_integer``: a finite double its integral part
equals. It is false on NaN, where ``fp.eq`` is, and on the infinities.
``finite`` holds for a double that is neither NaN nor an infinity, as
``math.isfinite``, and ``copysign`` and ``close`` are ``math.copysign`` and
``math.isclose``; the other `math` functions pyct follows are one IEEE
operation each, in `heads.OPERATORS`.

``%`` follows CPython's own steps, from C's ``fmod``, ``//`` is the floor
CPython's steps come to inside a bound (``floor_division``), and the four
roundings to an int read the integral double back as an Int. An Int meets a
double as Python converts it, rounding half to even (``from_int``).

A form here names the parts it reads more than once with ``let``, as
``m!``, ``q!``, ``k!``, ``e!``, ``r!``, ``d!``, ``x!`` and ``y!``. None of them can
capture a name in an operand, since render defines every part a form reads:
an operand is a leaf's constant, a literal, a name render defined or
declared, ``e!`` and a number and never one of these, or an int's
conversion of one of those. ``!`` is in no Python name.
"""

import math
import re
import struct
from collections.abc import Callable

# a double's three fields as cvc5 prints them: one sign bit, eleven exponent bits, fifty-two
# fraction bits
_VALUE = re.compile(r"\(fp #b(?P<sign>[01]) #b(?P<exponent>[01]{11}) #b(?P<fraction>[01]{52})\)")


# what names the assertion that holds a float leaf finite, before the leaf's symbol, so the
# unsat core cvc5 dumps says which leaves an unsat rests on. `!` is in no symbol, so the
# assertion's name never meets a constant
FINITE = "finite!"


def literal(value: float) -> str:
    """The SMT-LIB term cvc5 reads as exactly this double: its bit pattern."""
    (bits,) = struct.unpack(">Q", struct.pack(">d", value))
    text = f"{bits:064b}"
    return f"(fp #b{text[0]} #b{text[1:12]} #b{text[12:]})"


def decode(text: str) -> float:
    """The double a Float64 value, as cvc5 prints it, holds."""
    matched = _VALUE.fullmatch(text)
    if matched is None:
        raise ValueError(f"not a double in three fields: {text}")
    bits = int(matched["sign"] + matched["exponent"] + matched["fraction"], 2)
    (value,) = struct.unpack(">d", bits.to_bytes(8, "big"))
    return value


def held_finite(constant: str, symbol: str | None) -> str:
    """The assertion that holds one float leaf finite, named for the leaf's symbol if given, so
    the unsat core cvc5 dumps names it (``FINITE``)."""
    held = finite(constant)
    return f"(assert {held})" if symbol is None else f"(assert (! {held} :named {FINITE}{symbol}))"


def finite(term: str) -> str:
    """``term`` is neither NaN nor an infinity."""
    return f"(not (or (fp.isNaN {term}) (fp.isInfinite {term})))"


def unequal(left: str, right: str) -> str:
    """Python's ``!=`` on two doubles: not IEEE equal, so NaN is unequal to itself."""
    return f"(not (fp.eq {left} {right}))"


def minus(*operands: str) -> str:
    """Python's ``-``: the negation of one operand, or the difference of two."""
    if len(operands) == 1:
        return f"(fp.neg {operands[0]})"
    return f"(fp.sub RNE {' '.join(operands)})"


def whole(term: str) -> str:
    """Python's ``float.is_integer``: finite, and equal to its integral part."""
    return f"(and (not (fp.isInfinite {term})) (fp.eq (fp.roundToIntegral RTZ {term}) {term}))"


def from_int(term: str) -> str:
    """An Int term as the double Python converts it to, rounding half to even.

    Exact from -2**53 to 2**53; past that it is the nearest double, and past
    the largest double an infinity, where Python's own conversion raises.
    """
    return f"((_ to_fp 11 53) RNE (to_real {term}))"


def _to_int(mode: str) -> Callable[[str], str]:
    """A rounding to an int in one of IEEE's directions, as an Int term.

    The integral double is a whole number exactly, so reading it as a real
    and that as an Int loses nothing. Core records the finite fork first,
    so the term only meets a finite double on a path.
    """

    def rounded(term: str) -> str:
        return f"(to_int (fp.to_real (fp.roundToIntegral {mode} {term})))"

    return rounded


def copysign(magnitude: str, sign: str) -> str:
    """Python's ``math.copysign``: the first double's size with the second's sign.

    SMT-LIB's NaN has no sign, so a NaN ``sign`` counts as positive, as
    Python's own NaN, ``float('nan')``, is; a NaN made negative, as
    ``-float('nan')`` is, is not one this reads.
    """
    return f"(let ((x! (fp.abs {magnitude}))) (ite (fp.isNegative {sign}) (fp.neg x!) x!))"


def close(a: str, b: str, rel_tol: str, abs_tol: str) -> str:
    """Python's ``math.isclose``, CPython's ``math_isclose_impl`` step by step.

    Equal doubles are close, infinities included; otherwise an infinity is
    close to nothing, and two others are close when their difference is
    within the relative tolerance of either one or within the absolute
    tolerance. A NaN is close to nothing. Python refuses a negative
    tolerance before it compares, so the tolerances here are never one.
    """
    within = f"(fp.leq d! (fp.abs (fp.mul RNE {rel_tol} {{}})))"
    near = f"(or {within.format(b)} {within.format(a)} (fp.leq d! {abs_tol}))"
    finite = f"(not (fp.isInfinite {a})) (not (fp.isInfinite {b}))"
    apart = f"(let ((d! (fp.abs (fp.sub RNE {b} {a})))) {near})"
    return f"(or (fp.eq {a} {b}) (and {finite} {apart}))"


# `math.floor`, `math.ceil`, `math.trunc`, and `round` with no digits, which rounds half to even
floor = _to_int("RTN")
ceil = _to_int("RTP")
trunc = _to_int("RTZ")
rounded = _to_int("RNE")

_ZERO = literal(0.0)
_MINUS_ZERO = literal(-0.0)
_NAN = literal(math.nan)


def _signed_zero(term: str) -> str:
    """C's ``copysign(0.0, term)``: a zero with the sign of ``term``."""
    return f"(ite (fp.isNegative {term}) {_MINUS_ZERO} {_ZERO})"


def _undefined(dividend: str, divisor: str) -> str:
    """Where C's ``fmod`` has no number to give: a NaN, an infinite dividend, a zero divisor."""
    dividend_nan = f"(fp.isNaN {dividend}) (fp.isInfinite {dividend})"
    return f"(or {dividend_nan} (fp.isNaN {divisor}) (fp.isZero {divisor}))"


def _fmod(dividend: str, divisor: str) -> str:
    """C's ``fmod``: the remainder of the quotient cut toward zero, with the dividend's sign.

    Worked out in reals, where ``x - y * trunc(x / y)`` is exact: that
    remainder is always a double, so converting it back loses nothing. IEEE's
    own ``fp.rem`` is exact too, but cvc5 takes seconds on it where the reals
    take milliseconds. A NaN, an infinite dividend or a zero divisor gives
    NaN, and an infinite divisor hands the dividend back, as C's does.
    """
    ratio = "(let ((r! (/ x! y!))) (ite (>= r! 0.0) (to_int r!) (- (to_int (- r!)))))"
    exact = f"(- x! (* y! (to_real {ratio})))"
    reals = f"(let ((x! (fp.to_real {dividend})) (y! (fp.to_real {divisor}))) {exact})"
    zero = _signed_zero(dividend)
    signed = f"(let ((e! ((_ to_fp 11 53) RNE {reals}))) (ite (fp.isZero e!) {zero} e!))"
    undefined = _undefined(dividend, divisor)
    return f"(ite {undefined} {_NAN} (ite (fp.isInfinite {divisor}) {dividend} {signed}))"


def _shifted(divisor: str) -> str:
    """Whether CPython moves ``fmod``'s remainder, named ``m!``, to the divisor's side."""
    return f"(and (not (fp.isZero m!)) (not (= (fp.lt {divisor} {_ZERO}) (fp.lt m! {_ZERO}))))"


def modulo(dividend: str, divisor: str) -> str:
    """Python's ``%`` on two doubles, CPython's ``float_rem`` step by step.

    ``fmod``'s remainder, moved by the divisor when its sign differs from
    the divisor's, and a zero with the divisor's sign when it is zero:
    ``7.5 % -2.0`` is ``-0.5``.
    """
    moved = f"(ite {_shifted(divisor)} (fp.add RNE m! {divisor}) m!)"
    zero = _signed_zero(divisor)
    return f"(let ((m! {_fmod(dividend, divisor)})) (ite (fp.isZero m!) {zero} {moved}))"


# how far from zero a quotient may be for Python's float `//` to be its floor. CPython rounds
# the quotient twice on its way there, and below this bound the two together move it less than
# a half, which its last step snaps back
QUOTIENT_BOUND = 2**50


def _zero_like_quotient(dividend: str, divisor: str) -> str:
    """C's ``copysign(0.0, x / y)``: a zero, negative when exactly one of the two is."""
    same = f"(= (fp.isNegative {dividend}) (fp.isNegative {divisor}))"
    return f"(ite {same} {_ZERO} {_MINUS_ZERO})"


def floor_division(dividend: str, divisor: str, past: str | None = None) -> tuple[str, str]:
    """Python's ``//`` on two doubles, and the bound inside which the term is Python's.

    CPython's ``_float_div_mod`` divides the dividend less ``fmod``'s
    remainder, rounding twice, and snaps the result to a whole double. While
    the true quotient stays inside ``QUOTIENT_BOUND`` that is exactly its
    floor, worked out in reals, where cvc5 answers in milliseconds and its
    floating-point steps take seconds. A zero quotient takes the true
    quotient's sign. An infinite divisor gives -1.0 where the remainder moves
    to the divisor's side, as CPython's steps do, and a signed zero
    otherwise; NaN, an infinite dividend or a zero divisor give NaN.

    Given ``past``, the term past the bound is that Float64 constant, which
    render declares for this term alone, held only to what CPython's steps
    always give there:
    a whole double or an infinity, on the true quotient's side and at least
    ``_PAST_LEAST`` in size, since its two roundings move a quotient that
    large by a few parts in 2**52. Any other value reads as NaN. So the term
    can be whatever Python gives past the bound, and an unsat on it holds for
    every such value. Without ``past`` the term is the floor everywhere, for a
    program that holds the bound, where the two agree and cvc5 answers far
    faster (see ``Program.bounded``); that bound also says the floor converts
    to a finite double (``_quotient_inside``).
    """
    zero = _zero_like_quotient(dividend, divisor)
    floor_ = f"(let ((k! (to_int q!))) (ite (= k! 0) {zero} {from_int('k!')}))"
    reals = f"(let ((q! (/ (fp.to_real {dividend}) (fp.to_real {divisor})))) {{}})"
    signs = f"(= (fp.isNegative {dividend}) (fp.isNegative {divisor}))"
    moved = f"(and (not (fp.isZero {dividend})) (not {signs}))"
    past_infinity = f"(ite {moved} {literal(-1.0)} {zero})"
    undefined = _undefined(dividend, divisor)
    finite = f"(ite (fp.isInfinite {divisor}) {past_infinity} {reals.format(floor_)})"
    inside = _quotient_inside(held=past is None)
    bound = f"(or {undefined} (fp.isInfinite {divisor}) {reals.format(inside)})"
    exact = f"(ite {undefined} {_NAN} {finite})"
    if past is None:
        return exact, bound
    beyond = reals.format(f"(ite {_past_holds(past)} {past} {_NAN})")
    return f"(ite {bound} {exact} {beyond})", bound


def _quotient_inside(*, held: bool) -> str:
    """Whether the true quotient, named ``q!``, is inside the bound.

    In a program that holds the bound, ``held``, it says too that the quotient's floor converts
    to a finite double. A whole number below 2**50 in size always does, so the bound means what
    it did; said outright, the finite fork over a `//` flips in about 0.07 s, where cvc5 1.3.4
    took about 6 s to prove it and as long again for the unsat core. The term past the bound,
    which tests the bound rather than holds it, leaves it out: there it slowed
    ``x // 1.0 == 1e300`` from 0.3 s to 1.4 s.
    """
    inside = f"(and (< q! {QUOTIENT_BOUND}) (< (- {QUOTIENT_BOUND}) q!))"
    if not held:
        return inside
    return f"(and {inside} (not (fp.isInfinite {from_int('(to_int q!)')})))"


# how large CPython's `//` is past the bound, at the least: a quotient of 2**50 or more, moved
# by two roundings and a snap, stays far above this
_PAST_LEAST = 2.0**49


def _past_holds(past: str) -> str:
    """What CPython's `//` always is past the bound, the true quotient named ``q!``."""
    whole_or_infinite = f"(or (fp.isInfinite {past}) {whole(past)})"
    above = f"(fp.geq {past} {literal(_PAST_LEAST)})"
    below = f"(fp.leq {past} {literal(-_PAST_LEAST)})"
    return f"(and {whole_or_infinite} (ite (> q! 0.0) {above} {below}))"
