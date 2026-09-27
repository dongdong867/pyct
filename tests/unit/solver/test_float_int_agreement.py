"""cvc5 held against Python where ints meet doubles: `//`, `%`, the roundings and conversion."""

import itertools
import math
import operator
from collections.abc import Callable
from fractions import Fraction

from pyct.solver import floats
from pyct.solver.floats import QUOTIENT_BOUND, literal
from tests.unit.solver.agreement import asked, needs_cvc5
from tests.unit.solver.test_float_agreement import SPECIAL, _same

# doubles that make `//` and `%` round: a remainder a hair from the divisor, a quotient a hair
# from a whole number, subnormals, and quotients near the bound
DIVISION = [
    *SPECIAL,
    7.5,
    -7.5,
    -2.0,
    1e-300,
    -1e-300,
    1e300,
    0.30000000000000004,
    2.0**50 - 1.0,
    -(2.0**50),
    3.0 * 2.0**49,
]

# ints whose conversion rounds: exact up to 2**53, then half to even, then past the largest
# double
INTS = [0, 1, -1, 7, 2**53 - 1, 2**53, 2**53 + 1, 2**53 + 3, -(2**53) - 1, 10**20, -(10**308)]

ROUNDINGS: dict[str, tuple[Callable[[str], str], Callable[[float], int]]] = {
    "floor": (floats.floor, math.floor),
    "ceil": (floats.ceil, math.ceil),
    "trunc": (floats.trunc, math.trunc),
    "round": (floats.rounded, round),
}


def _values(sort: str, terms: list[str]) -> list[object]:
    """What cvc5 says each term is, each asked as a constant held equal to it."""
    lines = ["(set-logic ALL)"]
    for at, term in enumerate(terms):
        lines += [f"(declare-const v{at} {sort})", f"(assert (= v{at} {term}))"]
    lines += ["(check-sat)", f"(get-value ({' '.join(f'v{at}' for at in range(len(terms)))}))"]
    return asked(lines)


def _divided() -> list[tuple[float, float]]:
    """Every pair of the doubles above; a zero divisor raises in Python before it divides."""
    return [(x, y) for x, y in itertools.product(DIVISION, repeat=2) if y != 0]


@needs_cvc5
def test_cvc5_agrees_with_python_to_the_bit_on_modulo() -> None:
    pairs = _divided()

    said = _values("Float64", [floats.modulo(literal(x), literal(y)) for x, y in pairs])

    assert len(said) == len(pairs)
    wrong = [(x, y, s) for (x, y), s in zip(pairs, said, strict=True) if not _same(s, x % y)]
    assert wrong == []


def _inside(x: float, y: float) -> bool:
    """Whether a quotient is inside the bound floor division holds, as Python has it."""
    if not (math.isfinite(x) and math.isfinite(y)):
        return True
    return abs(Fraction(x) / Fraction(y)) < QUOTIENT_BOUND


@needs_cvc5
def test_cvc5_agrees_with_python_to_the_bit_on_floor_division_inside_its_bound() -> None:
    pairs = _divided()
    written = [floats.floor_division(literal(x), literal(y)) for x, y in pairs]

    quotients = _values("Float64", [term for term, _ in written])
    bounds = _values("Bool", [bound for _, bound in written])

    # the bound is Python's own: it holds exactly where the true quotient is inside it
    assert bounds == [_inside(x, y) for x, y in pairs]
    wrong = [
        (x, y, said)
        for (x, y), said, inside in zip(pairs, quotients, bounds, strict=True)
        if inside and not _same(said, x // y)
    ]
    assert wrong == []
    # the doubles reach past the bound too, so a clean result is not a narrow one
    assert False in bounds


@needs_cvc5
def test_cvc5_agrees_with_python_on_every_rounding_of_a_finite_double() -> None:
    values = [value for value in DIVISION if math.isfinite(value)] + [0.5, 1.5, -0.5, 2.5]
    cases = list(itertools.product(ROUNDINGS, values))

    said = _values("Int", [ROUNDINGS[head][0](literal(value)) for head, value in cases])

    meant = [ROUNDINGS[head][1](value) for head, value in cases]
    assert said == meant


@needs_cvc5
def test_cvc5_converts_an_int_to_the_double_python_does() -> None:
    said = _values("Float64", [floats.from_int(str(n) if n >= 0 else f"(- {-n})") for n in INTS])

    assert [_same(value, float(n)) for value, n in zip(said, INTS, strict=True)] == [True] * len(
        INTS
    )


@needs_cvc5
def test_cvc5_agrees_with_python_where_an_int_meets_a_double() -> None:
    doubles = [0.5, -2.5, 0.1, 1e300]
    cases = list(itertools.product(INTS, doubles, [operator.add, operator.mul, operator.lt]))
    terms = {operator.add: "fp.add RNE", operator.mul: "fp.mul RNE", operator.lt: "fp.lt"}

    def term(n: int, f: float, op: Callable[..., object]) -> str:
        return f"({terms[op]} {floats.from_int(str(n) if n >= 0 else f'(- {-n})')} {literal(f)})"

    exact = [case for case in cases if abs(case[0]) <= 2**53]
    sums = _values("Float64", [term(n, f, op) for n, f, op in exact if op is not operator.lt])
    orders = _values("Bool", [term(n, f, op) for n, f, op in exact if op is operator.lt])

    arithmetic = [(n, f, op) for n, f, op in exact if op is not operator.lt]
    assert all(_same(s, op(n, f)) for s, (n, f, op) in zip(sums, arithmetic, strict=True))
    compares = [(n, f) for n, f, op in exact if op is operator.lt]
    assert orders == [n < f for n, f in compares]
