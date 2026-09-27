"""A path on tracked floats written out as SMT-LIB's IEEE doubles."""

import math
import re
from collections.abc import Collection

import pytest

from pyct.core.branch import Branch, Expression
from pyct.solver.floats import finite, literal, minus, unequal, whole
from pyct.solver.render import float_leaves, program
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


def test_a_power_on_doubles_is_an_error_since_nothing_encodes_it() -> None:
    # core keeps `**` on a float a downgrade: no solver operation gives CPython's pow to the bit
    with pytest.raises(ValueError, match=re.escape("** on float")):
        _lines(["==", ["**", "x", 2.0], 1.0])


def _finite_lines(
    prefix: tuple[Branch, ...],
    leaves: dict[str, type],
    finite: Collection[str],
    *,
    cores: bool = False,
) -> list[str]:
    return program(prefix, leaves, finite=finite, cores=cores).text.splitlines()


def test_the_finite_ask_holds_each_float_leaf_it_names_finite_before_the_path() -> None:
    prefix = (fork(["<", "n", 3], taken=True), fork([">", "x", 2.5], taken=False))

    lines = _finite_lines(prefix, {"n": int, "x": float, "y": float}, {"x", "y"})

    # y is on no fork, so it is not declared or held, and n is an int. The first ask asks for
    # no unsat core, which slows some sat answers
    assert lines[:5] == [
        "(set-logic ALL)",
        f"(declare-const {N} Int)",
        f"(declare-const {X} Float64)",
        f"(assert {finite(X)})",
        f"(assert (< {N} 3))",
    ]
    assert Y not in "\n".join(lines)


def test_an_ask_for_the_core_names_each_held_leaf() -> None:
    prefix = (fork(["<", "n", 3], taken=True), fork([">", "x", 2.5], taken=False))

    lines = _finite_lines(prefix, {"n": int, "x": float}, {"x"}, cores=True)

    # each held leaf is named for its symbol, so cvc5's dumped unsat core says which of them
    # the unsat rests on
    assert lines[:5] == [
        "(set-option :dump-unsat-cores true)",
        "(set-logic ALL)",
        f"(declare-const {N} Int)",
        f"(declare-const {X} Float64)",
        f"(assert (! {finite(X)} :named finite!arg.x))",
    ]


def test_a_leaf_left_out_of_the_finite_ask_may_be_any_double() -> None:
    prefix = (fork(["==", "x", "y"], taken=False),)

    lines = _finite_lines(prefix, {"x": float, "y": float}, {"y"})

    assert f"(assert {finite(Y)})" in lines
    assert f"fp.isNaN {X}" not in "\n".join(lines)


def test_a_finite_ask_holding_no_leaf_is_the_path_itself() -> None:
    prefix = (fork([">", "x", 2.5], taken=True),)

    plain = render(prefix, {"x": float})
    assert program(prefix, {"x": float}, finite=()).text == plain
    assert program(prefix, {"x": float}, finite={"n"}).text == plain
    assert program(prefix, {"x": float}, finite=(), cores=True).text == plain


def test_the_float_leaves_are_those_a_fork_names() -> None:
    leaves = {"n": int, "x": float, "y": float}

    assert float_leaves((fork([">", ["abs", "x"], "y"], taken=True),), leaves) == {"x", "y"}
    assert float_leaves((fork([">", "x", 1.0], taken=True),), leaves) == {"x"}
    assert float_leaves((fork(["<", "n", 3], taken=True),), leaves) == set()
    assert float_leaves((fork(["<", "n", 3], taken=True),), {"n": int}) == set()
    assert float_leaves((), leaves) == set()
