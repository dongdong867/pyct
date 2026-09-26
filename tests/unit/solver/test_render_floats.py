"""A path on tracked floats written out as SMT-LIB's IEEE doubles."""

import math
import re

import pytest

from pyct.core.branch import Expression
from pyct.solver.floats import finite, literal, minus, unequal, whole
from pyct.solver.render import names_a_float, program
from tests.unit.solver.test_render import fork, render

# each compare on doubles as the expression carries it, and the operator the program writes.
# `==` is IEEE equality, never SMT-LIB's `=`, which calls NaN equal to itself
COMPARES = {"<": "fp.lt", "<=": "fp.leq", ">": "fp.gt", ">=": "fp.geq", "==": "fp.eq"}

# each operation on doubles as the expression carries it, and the term the program writes for
# it. Every one rounds to nearest even, as CPython does
OPERATIONS: dict[str, tuple[Expression, str]] = {
    "plus": (["+", "x", "y"], "(fp.add RNE |arg.x| |arg.y|)"),
    "minus": (["-", "x", "y"], minus("|arg.x|", "|arg.y|")),
    "times": (["*", "x", "y"], "(fp.mul RNE |arg.x| |arg.y|)"),
    "divided": (["/", "x", "y"], "(fp.div RNE |arg.x| |arg.y|)"),
    "negated": (["-", "x"], minus("|arg.x|")),
    "abs": (["abs", "x"], "(fp.abs |arg.x|)"),
    "literal-first": (["-", 10.0, "x"], f"(fp.sub RNE {literal(10.0)} |arg.x|)"),
}

FLOAT_LEAVES: dict[str, type] = {"x": float, "y": float}

# the constant each leaf is declared as
X, Y, N = "|arg.x|", "|arg.y|", "|arg.n|"


def _lines(expression: Expression, leaves: dict[str, type] = FLOAT_LEAVES) -> list[str]:
    return render((fork(expression, taken=True),), leaves).splitlines()


def test_a_float_leaf_is_declared_a_double() -> None:
    assert _lines([">", "x", 2.5]) == [
        "(set-logic ALL)",
        f"(declare-const {X} Float64)",
        f"(assert (fp.gt {X} {literal(2.5)}))",
        "(check-sat)",
        f"(get-value ({X}))",
    ]


@pytest.mark.parametrize(("op", "operator"), COMPARES.items(), ids=list(COMPARES))
def test_a_compare_on_doubles_is_ieees_own(op: str, operator: str) -> None:
    assert f"(assert ({operator} {X} {Y}))" in _lines([op, "x", "y"])


def test_unequal_doubles_are_not_ieee_equal() -> None:
    # the truth test of a float is its inequality with zero, which -0.0 fails as 0.0 does
    assert f"(assert {unequal(X, literal(0.0))})" in _lines(["!=", "x", 0.0])


@pytest.mark.parametrize(("expression", "term"), OPERATIONS.values(), ids=list(OPERATIONS))
def test_an_operation_on_doubles_is_written_as_the_term_that_means_it(
    expression: Expression, term: str
) -> None:
    assert f"(assert (fp.lt {term} {literal(1.0)}))" in _lines(["<", expression, 1.0])


def test_is_integer_is_a_finite_double_equal_to_its_integral_part() -> None:
    assert f"(assert {whole(X)})" in _lines(["is_integer", "x"])


@pytest.mark.parametrize("value", [-3.0, -0.0, math.nan, -math.inf, 5e-324])
def test_a_float_literal_is_written_as_its_bit_pattern(value: float) -> None:
    # a negative double is one bit pattern, not a subtraction as a negative int is
    assert f"(assert (fp.eq {X} {literal(value)}))" in _lines(["==", "x", value])


def test_a_quotient_is_a_float_whatever_its_operands() -> None:
    lines = _lines([">", ["/", "x", "y"], 2.5])

    assert f"(assert (fp.gt (fp.div RNE {X} {Y}) {literal(2.5)}))" in lines


def test_a_float_part_held_twice_is_defined_once_as_a_double() -> None:
    part: Expression = ["*", "x", "x"]

    lines = _lines(["==", ["+", part, part], 8.0])

    assert f"(define-fun e!0 () Float64 (fp.mul RNE {X} {X}))" in lines
    assert f"(assert (fp.eq (fp.add RNE e!0 e!0) {literal(8.0)}))" in lines


@pytest.mark.parametrize("head", ["//", "%", "**"])
def test_an_operation_on_doubles_nothing_encodes_is_an_error(head: str) -> None:
    with pytest.raises(ValueError, match=re.escape(f"{head} on float")):
        _lines(["==", [head, "x", 2.0], 1.0])


def test_the_finite_ask_holds_each_float_leaf_finite_before_the_path() -> None:
    prefix = (fork(["<", "n", 3], taken=True), fork([">", "x", 2.5], taken=False))

    leaves = {"n": int, "x": float, "y": float}
    lines = program(prefix, leaves, finite=True).text.splitlines()

    # y is on no fork, so it is not declared, and n is an int, which is always finite
    assert lines[:5] == [
        "(set-logic ALL)",
        f"(declare-const {N} Int)",
        f"(declare-const {X} Float64)",
        f"(assert {finite(X)})",
        f"(assert (< {N} 3))",
    ]
    assert Y not in "\n".join(lines)


def test_the_finite_ask_on_a_path_of_no_float_is_the_path_itself() -> None:
    prefix = (fork(["<", "n", 3], taken=True),)

    assert program(prefix, {"n": int}, finite=True).text == render(prefix, {"n": int})


def test_a_path_names_a_float_when_a_fork_names_a_float_leaf() -> None:
    leaves = {"n": int, "x": float}

    assert names_a_float((fork([">", ["abs", "x"], 1.0], taken=True),), leaves)
    assert not names_a_float((fork(["<", "n", 3], taken=True),), leaves)
    assert not names_a_float((fork(["<", "n", 3], taken=True),), {"n": int})
    assert not names_a_float((), leaves)
