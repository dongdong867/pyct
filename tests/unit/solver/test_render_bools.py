"""A condition used as a value: a Bool term, read as the Int 1 or 0 where a number is needed."""

from collections.abc import Callable

import pytest

from pyct.core.branch import Branch, Expression, Site
from pyct.solver.cvc5 import Sat, Unsat, solve
from tests.unit.solver.test_render import render
from tests.unit.solver.test_render_types import BOOL_TERMS, TYPED_LEAVES, _head
from tests.unit.solver.test_render_types import _asserted as _assertion_in

SITE = Site(file="m.py", line=2, col=7)
ABOVE: Expression = [">", "x", 0]
BELOW: Expression = [">", "y", 0]
INTS: dict[str, type] = {"x": int, "y": int}

# a condition, and the term render asserts for it
WRITTEN: dict[str, tuple[Expression, str]] = {
    "a count of conditions": (
        ["==", ["+", ABOVE, BELOW], 2],
        "(= (+ (ite (> |arg.x| 0) 1 0) (ite (> |arg.y| 0) 1 0)) 2)",
    ),
    "a true literal in a sum": ([">", ["+", "x", True], 5], "(> (+ |arg.x| 1) 5)"),
    "an int equal to a false literal": (["==", "x", False], "(= |arg.x| 0)"),
    "a bool equal to an int": (["==", ABOVE, 1], "(= (ite (> |arg.x| 0) 1 0) 1)"),
    "an order on two bools": (
        ["<", ABOVE, BELOW],
        "(< (ite (> |arg.x| 0) 1 0) (ite (> |arg.y| 0) 1 0))",
    ),
    "a negated bool": (["<", ["-", ABOVE], 0], "(< (- (ite (> |arg.x| 0) 1 0)) 0)"),
    "a power of a literal": (["==", ["**", "x", True], 3], "(= (^ |arg.x| 1) 3)"),
    "and": (["&", ABOVE, BELOW], "(and (> |arg.x| 0) (> |arg.y| 0))"),
    "or": (["|", ABOVE, BELOW], "(or (> |arg.x| 0) (> |arg.y| 0))"),
    "xor": (["^", ABOVE, BELOW], "(xor (> |arg.x| 0) (> |arg.y| 0))"),
    "and with a literal": (["&", ABOVE, True], "(and (> |arg.x| 0) true)"),
    "two bools equal": (["==", ABOVE, BELOW], "(= (> |arg.x| 0) (> |arg.y| 0))"),
    "two bools unequal": (["!=", ABOVE, BELOW], "(distinct (> |arg.x| 0) (> |arg.y| 0))"),
    "a bool equal to a literal": (["==", ABOVE, True], "(= (> |arg.x| 0) true)"),
}


def _asserted(expression: Expression) -> str:
    """The one assertion a one-fork program holds, for the fork taken."""
    return _assertion_in(render((Branch(expression=expression, taken=True, site=SITE),), INTS))


@pytest.mark.parametrize(("expression", "term"), WRITTEN.values(), ids=list(WRITTEN))
def test_a_bool_meets_an_int_as_the_int_1_or_0(expression: Expression, term: str) -> None:
    assert _asserted(expression) == f"(assert {term})"


@pytest.mark.parametrize("term", BOOL_TERMS, ids=[_head(term) for term in BOOL_TERMS])
def test_a_head_that_builds_a_bool_is_ordered_as_the_int_1_or_0(term: Expression) -> None:
    text = render((Branch(expression=["<", term, "n"], taken=True, site=SITE),), TYPED_LEAVES)

    # Python orders a bool as the int it is, so the term is read as 1 or 0
    assert _assertion_in(text).startswith("(assert (< (ite ")


def test_a_division_by_a_bool_divides_by_1_or_0() -> None:
    text = render((Branch(expression=["==", ["//", 10, ABOVE], 10], taken=True, site=SITE),), INTS)

    # a form's operand is defined once, as the bool it is, and the form reads it as a number
    divisor = "(ite e!0 1 0)"
    assert text.splitlines()[2:4] == [
        "(define-fun e!0 () Bool (> |arg.x| 0))",
        f"(assert (= (ite (or (> {divisor} 0) (= (mod 10 {divisor}) 0))"
        f" (div 10 {divisor}) (- (div 10 {divisor}) 1)) 10))",
    ]


# a division form on two bools: the condition, and the term the form writes. Each bool is read
# by the form as the number it is, defined once as the Bool it is
BOTH = ("(ite e!0 1 0)", "(ite e!1 1 0)")
AGREES = f"(or (> {BOTH[1]} 0) (= (mod {BOTH[0]} {BOTH[1]}) 0))"
FORMS_ON_TWO_BOOLS: dict[str, tuple[Expression, str]] = {
    "//": (
        ["==", ["//", ABOVE, BELOW], 1],
        f"(= (ite {AGREES} (div {BOTH[0]} {BOTH[1]}) (- (div {BOTH[0]} {BOTH[1]}) 1)) 1)",
    ),
    "%": (
        ["==", ["%", ABOVE, BELOW], 0],
        f"(= (ite {AGREES} (mod {BOTH[0]} {BOTH[1]}) (+ (mod {BOTH[0]} {BOTH[1]}) {BOTH[1]})) 0)",
    ),
}


@pytest.mark.parametrize(
    ("expression", "term"), FORMS_ON_TWO_BOOLS.values(), ids=list(FORMS_ON_TWO_BOOLS)
)
def test_a_division_of_two_bools_divides_their_numbers(expression: Expression, term: str) -> None:
    text = render((Branch(expression=expression, taken=True, site=SITE),), INTS)

    assert text.splitlines()[3:6] == [
        "(define-fun e!0 () Bool (> |arg.x| 0))",
        "(define-fun e!1 () Bool (> |arg.y| 0))",
        f"(assert {term})",
    ]


FLOORED: Expression = ["==", ["//", ABOVE, BELOW], 1]
REMAINDER: Expression = ["==", ["%", ABOVE, BELOW], 0]


def _floored(x: int, y: int) -> bool:
    return (x > 0) // (y > 0) == 1


def _remainder(x: int, y: int) -> bool:
    return (x > 0) % (y > 0) == 0


@pytest.mark.parametrize(
    ("expression", "taken", "python"),
    [
        pytest.param(FLOORED, True, _floored, id="// taken"),
        pytest.param(FLOORED, False, _floored, id="// not taken"),
        pytest.param(REMAINDER, True, _remainder, id="% taken"),
    ],
)
def test_cvc5_divides_two_bools_past_the_divisors_fork_as_python_does(
    expression: Expression, taken: bool, python: Callable[[int, int], bool]
) -> None:
    # core records the divisor's own condition, taken, before it divides
    prefix = (
        Branch(expression=BELOW, taken=True, site=SITE),
        Branch(expression=expression, taken=taken, site=SITE),
    )

    answer = solve(prefix, INTS, 10.0)

    assert isinstance(answer, Sat), answer
    x, y = (answer.model.get(name, 0) for name in ("x", "y"))
    assert isinstance(x, int) and isinstance(y, int)
    assert y > 0 and python(x, y) is taken


def test_cvc5_finds_no_bool_left_over_from_a_true_divisor() -> None:
    # a bool modulo a true bool is always 0, in Python and in the program render writes
    prefix = (
        Branch(expression=BELOW, taken=True, site=SITE),
        Branch(expression=REMAINDER, taken=False, site=SITE),
    )

    assert isinstance(solve(prefix, INTS, 10.0), Unsat)


def test_a_bool_held_twice_is_defined_once_as_a_bool() -> None:
    held: Expression = [">", "x", 0]
    prefix = (
        Branch(expression=held, taken=True, site=SITE),
        Branch(expression=["==", ["+", held, held], 2], taken=True, site=SITE),
    )

    lines = render(prefix, INTS).splitlines()

    assert "(define-fun e!0 () Bool (> |arg.x| 0))" in lines
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


# a bool parameter: its leaf, and the term render asserts for a condition on it
FLAG_LEAVES: dict[str, type] = {"flag": bool, "x": int, "f": float}
FLAG_WRITTEN: dict[str, tuple[Expression, str]] = {
    "the parameter alone": ("flag", "|arg.flag|"),
    "the parameter in a sum": (
        [">", ["+", "flag", "x"], 5],
        "(> (+ (ite |arg.flag| 1 0) |arg.x|) 5)",
    ),
    "the parameter equal to an int": (["==", "flag", 1], "(= (ite |arg.flag| 1 0) 1)"),
    "the parameter and a condition": (["&", "flag", ABOVE], "(and |arg.flag| (> |arg.x| 0))"),
}


@pytest.mark.parametrize(("expression", "term"), FLAG_WRITTEN.values(), ids=list(FLAG_WRITTEN))
def test_a_bool_parameter_is_a_bool_leaf(expression: Expression, term: str) -> None:
    text = render((Branch(expression=expression, taken=True, site=SITE),), FLAG_LEAVES)

    assert "(declare-const |arg.flag| Bool)" in text.splitlines()
    assert _assertion_in(text) == f"(assert {term})"


def test_a_bool_parameter_is_the_double_1_or_0_beside_a_float() -> None:
    expression: Expression = [">", ["*", "flag", 2.5], "f"]

    text = render((Branch(expression=expression, taken=True, site=SITE),), FLAG_LEAVES)

    assert "(ite |arg.flag| 1 0)" in _assertion_in(text)


def test_the_solver_flips_a_bool_parameter() -> None:
    prefix = (Branch(expression="flag", taken=True, site=SITE),)

    answer = solve(prefix, {"flag": bool}, timeout=10.0)

    assert answer == Sat(model={"flag": True})
    assert isinstance(answer, Sat)
    assert type(answer.model["flag"]) is bool


def test_the_solver_reads_a_bool_parameter_as_1_or_0_in_a_sum() -> None:
    expression: Expression = [">", ["+", "flag", "x"], 5]
    prefix = (Branch(expression=expression, taken=True, site=SITE),)

    answer = solve(prefix, {"flag": bool, "x": int}, timeout=10.0)

    assert isinstance(answer, Sat)
    flag, x = answer.model["flag"], answer.model["x"]
    assert isinstance(flag, bool) and isinstance(x, int)
    assert flag + x > 5


def test_a_bool_parameter_true_and_false_at_once_is_unsat() -> None:
    prefix = (
        Branch(expression="flag", taken=True, site=SITE),
        Branch(expression="flag", taken=False, site=SITE),
    )

    assert solve(prefix, {"flag": bool}, timeout=10.0) == Unsat()
