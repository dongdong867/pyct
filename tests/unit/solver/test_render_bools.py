"""A condition used as a value: a Bool term, read as the Int 1 or 0 where a number is needed."""

import pytest

from pyct.core.branch import Branch, Expression, Site
from pyct.solver.cvc5 import Sat, solve
from pyct.solver.render import render

SITE = Site(file="m.py", line=2, col=7)
ABOVE: Expression = [">", "x", 0]
BELOW: Expression = [">", "y", 0]
INTS: dict[str, type] = {"x": int, "y": int}

# a condition, and the term render asserts for it
WRITTEN: dict[str, tuple[Expression, str]] = {
    "a count of conditions": (
        ["==", ["+", ABOVE, BELOW], 2],
        "(= (+ (ite (> x 0) 1 0) (ite (> y 0) 1 0)) 2)",
    ),
    "a true literal in a sum": ([">", ["+", "x", True], 5], "(> (+ x 1) 5)"),
    "an int equal to a false literal": (["==", "x", False], "(= x 0)"),
    "a bool equal to an int": (["==", ABOVE, 1], "(= (ite (> x 0) 1 0) 1)"),
    "an order on two bools": (["<", ABOVE, BELOW], "(< (ite (> x 0) 1 0) (ite (> y 0) 1 0))"),
    "a negated bool": (["<", ["-", ABOVE], 0], "(< (- (ite (> x 0) 1 0)) 0)"),
    "a power of a literal": (["==", ["**", "x", True], 3], "(= (^ x 1) 3)"),
    "and": (["&", ABOVE, BELOW], "(and (> x 0) (> y 0))"),
    "or": (["|", ABOVE, BELOW], "(or (> x 0) (> y 0))"),
    "xor": (["^", ABOVE, BELOW], "(xor (> x 0) (> y 0))"),
    "and with a literal": (["&", ABOVE, True], "(and (> x 0) true)"),
    "two bools equal": (["==", ABOVE, BELOW], "(= (> x 0) (> y 0))"),
    "two bools unequal": (["!=", ABOVE, BELOW], "(distinct (> x 0) (> y 0))"),
    "a bool equal to a literal": (["==", ABOVE, True], "(= (> x 0) true)"),
}


def _asserted(expression: Expression) -> str:
    """The one assertion a one-fork program holds, for the fork taken."""
    text = render((Branch(expression=expression, taken=True, site=SITE),), INTS)
    return next(line for line in text.splitlines() if line.startswith("(assert "))


@pytest.mark.parametrize(("expression", "term"), WRITTEN.values(), ids=list(WRITTEN))
def test_a_bool_meets_an_int_as_the_int_1_or_0(expression: Expression, term: str) -> None:
    assert _asserted(expression) == f"(assert {term})"


def test_a_division_by_a_bool_divides_by_1_or_0() -> None:
    text = render((Branch(expression=["==", ["//", 10, ABOVE], 10], taken=True, site=SITE),), INTS)

    # a form's operand is defined once, as the bool it is, and the form reads it as a number
    divisor = "(ite e!0 1 0)"
    assert text.splitlines()[2:4] == [
        "(define-fun e!0 () Bool (> x 0))",
        f"(assert (= (ite (or (> {divisor} 0) (= (mod 10 {divisor}) 0))"
        f" (div 10 {divisor}) (- (div 10 {divisor}) 1)) 10))",
    ]


def test_a_bool_held_twice_is_defined_once_as_a_bool() -> None:
    held: Expression = [">", "x", 0]
    prefix = (
        Branch(expression=held, taken=True, site=SITE),
        Branch(expression=["==", ["+", held, held], 2], taken=True, site=SITE),
    )

    lines = render(prefix, INTS).splitlines()

    assert "(define-fun e!0 () Bool (> x 0))" in lines
    assert "(assert e!0)" in lines
    assert "(assert (= (+ (ite e!0 1 0) (ite e!0 1 0)) 2))" in lines


@pytest.mark.parametrize(
    ("expression", "holds"),
    [
        pytest.param(["==", ["+", ABOVE, BELOW], 2], lambda x, y: (x > 0) + (y > 0) == 2, id="+"),
        pytest.param(["^", ABOVE, BELOW], lambda x, y: (x > 0) ^ (y > 0), id="^"),
        pytest.param(
            ["==", ["//", 7, ABOVE], 7], lambda x, y: x > 0 and 7 // (x > 0) == 7, id="//"
        ),
        pytest.param([">", ["+", "x", True], 5], lambda x, y: x + True > 5, id="literal"),
    ],
)
def test_cvc5_answers_a_bool_used_as_a_number_as_python_does(
    expression: Expression, holds: object
) -> None:
    answer = solve((Branch(expression=expression, taken=True, site=SITE),), INTS, 10.0)

    assert isinstance(answer, Sat), answer
    model = {"x": 0, "y": 0, **answer.model}
    assert callable(holds)
    assert holds(model["x"], model["y"]) is True
