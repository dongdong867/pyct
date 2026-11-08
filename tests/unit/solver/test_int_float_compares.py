"""cvc5 held against Python where an int is compared with a float, which Python does exactly."""

import itertools
import math
import operator
import subprocess
from collections.abc import Callable

import pytest

from pyct.core.foundation.branch import Expression
from pyct.solver.floats import literal
from pyct.solver.literals import leaf_term
from pyct.solver.render import program
from tests.unit.solver.agreement import needs_cvc5
from tests.unit.solver.test_cvc5 import fork

COMPARES: dict[str, Callable[[float, float], bool]] = {
    "<": operator.lt,
    "<=": operator.le,
    ">": operator.gt,
    ">=": operator.ge,
    "==": operator.eq,
    "!=": operator.ne,
}

# ints on either side of where a double stops holding every int
INTS = [2**53 - 1, 2**53, 2**53 + 1, -(2**53 + 1), 0]
FLOATS = [0.0, -0.0, 2.0**53, 2.0**53 + 2, 1e308, math.inf, -math.inf, math.nan]

LEAVES: dict[str, type] = {"n": int, "x": float}
N, X = "|arg.n|", "|arg.x|"

# one case: the int, the float, whether the int is on the left, and which of the two are tracked
type Case = tuple[int, float, bool, tuple[bool, bool]]

# the int tracked and the float a constant or tracked, as the criterion asks
TRACKED_INT = [(True, False), (True, True)]


def _checked(head: str, case: Case, *, taken: bool) -> list[str]:
    """The program render writes for the compare taken or not, each tracked leaf held to the
    case's value, as one scope of an incremental script."""
    n, value, left, (whole, double) = case
    operands: list[Expression] = ["n" if whole else n, "x" if double else value]
    expression = [head, *(operands if left else reversed(operands))]
    text = program((fork(expression, taken=taken),), LEAVES).text
    lines = [line for line in text.splitlines() if not line.startswith(("(set-", "(get-"))]
    pins = [f"(assert (= {N} {leaf_term(n)}))"] if whole else []
    if double:
        # SMT-LIB's `=` is sameness, so the pin holds -0.0 and NaN exactly
        pins.append(f"(assert (= {X} {literal(value)}))")
    at = lines.index("(check-sat)")
    return ["(push 1)", *lines[:at], *pins, *lines[at:], "(pop 1)"]


def _answers(head: str, cases: list[Case]) -> list[tuple[str, ...]]:
    """What cvc5 answers for each case, the compare true and then false, in one run."""
    lines = ["(set-option :incremental true)", "(set-logic ALL)"]
    for case in cases:
        lines += _checked(head, case, taken=True) + _checked(head, case, taken=False)
    said = subprocess.run(
        ["cvc5", "--lang", "smt", "--quiet"],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.split()
    assert len(said) == 2 * len(cases), said
    return list(itertools.batched(said, 2))


def _python(head: str, case: Case) -> bool:
    """What Python says of the compare, in this run."""
    n, value, left, _ = case
    return COMPARES[head](n, value) if left else COMPARES[head](value, n)


def _wrong(head: str, cases: list[Case]) -> list[tuple[Case, tuple[str, ...]]]:
    """Each case where cvc5 does not answer sat for Python's side alone."""
    answers = _answers(head, cases)
    meant = [("sat", "unsat") if _python(head, case) else ("unsat", "sat") for case in cases]
    return [
        (case, said) for case, said, ok in zip(cases, answers, meant, strict=True) if said != ok
    ]


# compare-an-int-with-a-float-exactly-matches-python
@needs_cvc5
@pytest.mark.parametrize("head", COMPARES)
def test_an_int_compared_with_a_float_has_one_side_sat_and_it_is_pythons(head: str) -> None:
    cases = list(itertools.product(INTS, FLOATS, [True, False], TRACKED_INT))

    assert _wrong(head, cases) == []


# a plain int a double does not hold, beside one it does
PLAIN_INTS = [2**53 + 1, -(2**53 + 1), 2**53 + 3, 10**400, 2**53, 0]


@needs_cvc5
@pytest.mark.parametrize("head", COMPARES)
def test_a_tracked_float_compared_with_a_plain_int_is_compared_exactly(head: str) -> None:
    cases = list(itertools.product(PLAIN_INTS, FLOATS, [True, False], [(False, True)]))

    assert _wrong(head, cases) == []
