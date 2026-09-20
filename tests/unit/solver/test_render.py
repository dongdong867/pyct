import pytest

from pyct.core.branch import Branch, Expression, Site
from pyct.solver.render import render

SITE = Site(file="m.py", line=2, col=7)


def fork(expression: Expression, *, taken: bool) -> Branch:
    """A fork at one fixed site: only the condition and the side matter here."""
    return Branch(expression=expression, taken=taken, site=SITE)


def test_a_taken_fork_becomes_a_whole_little_program() -> None:
    text = render((fork(["<", "x", 10], taken=True),), {"x": int})

    assert text.splitlines() == [
        "(set-logic ALL)",
        "(declare-const x Int)",
        "(assert (< x 10))",
        "(check-sat)",
        "(get-value (x))",
    ]


def test_a_fork_the_run_did_not_take_is_asserted_the_other_way() -> None:
    text = render((fork(["<", "x", 10], taken=False),), {"x": int})

    assert "(assert (not (< x 10)))" in text.splitlines()


def test_a_negative_number_is_written_as_a_subtraction() -> None:
    text = render((fork(["<", "x", -5], taken=True),), {"x": int})

    assert "(assert (< x (- 5)))" in text.splitlines()


def test_the_two_equality_operators_are_written_the_way_smt_spells_them() -> None:
    same = render((fork(["==", "x", 10], taken=True),), {"x": int})
    other = render((fork(["!=", "x", 10], taken=True),), {"x": int})

    assert "(assert (= x 10))" in same.splitlines()
    assert "(assert (distinct x 10))" in other.splitlines()


def test_arithmetic_is_written_under_its_own_name() -> None:
    text = render((fork([">", ["-", ["*", ["+", "x", 1], 2], 3], 10], taken=True),), {"x": int})

    assert "(assert (> (- (* (+ x 1) 2) 3) 10))" in text.splitlines()


def test_a_builtin_and_a_unary_minus_are_written_by_arity() -> None:
    text = render(
        (fork([">", ["abs", "x"], 5], taken=True), fork(["<", ["-", "x"], -3], taken=True)),
        {"x": int},
    )

    assert "(assert (> (abs x) 5))" in text.splitlines()
    assert "(assert (< (- x) (- 3)))" in text.splitlines()


def test_a_power_is_written_with_a_caret() -> None:
    text = render((fork(["==", ["**", "x", 2], 9], taken=True),), {"x": int})

    assert "(assert (= (^ x 2) 9))" in text.splitlines()


def test_floor_division_is_written_as_smts_own_with_the_floor_correction() -> None:
    # SMT-LIB's div is Euclidean, so Python's quotient is one lower exactly when the
    # divisor is negative and something is left over: division-floor-correction-in-render
    text = render((fork(["==", ["//", "x", "y"], 4], taken=True),), {"x": int, "y": int})

    assert "(assert (= (ite (or (> y 0) (= (mod x y) 0)) (div x y) (- (div x y) 1)) 4))" in (
        text.splitlines()
    )


def test_modulo_is_written_as_smts_own_shifted_onto_the_divisors_sign() -> None:
    text = render((fork(["==", ["%", "x", "y"], 1], taken=True),), {"x": int, "y": int})

    assert "(assert (= (ite (or (> y 0) (= (mod x y) 0)) (mod x y) (+ (mod x y) y)) 1))" in (
        text.splitlines()
    )


def test_a_negative_divisor_reaches_the_forms_already_written_as_a_subtraction() -> None:
    quotient = render((fork(["==", ["//", "x", -2], -4], taken=True),), {"x": int})
    remainder = render((fork(["==", ["%", "x", -3], -1], taken=True),), {"x": int})

    # a form joins rendered text, so `-2` arrives spelled the way every other operand is
    assert (
        "(assert (= (ite (or (> (- 2) 0) (= (mod x (- 2)) 0))"
        " (div x (- 2)) (- (div x (- 2)) 1)) (- 4)))" in quotient.splitlines()
    )
    assert (
        "(assert (= (ite (or (> (- 3) 0) (= (mod x (- 3)) 0))"
        " (mod x (- 3)) (+ (mod x (- 3)) (- 3))) (- 1)))" in remainder.splitlines()
    )


def test_an_operator_nothing_encodes_is_an_error() -> None:
    with pytest.raises(ValueError, match="<<"):
        render((fork(["<<", "x", 1], taken=True),), {"x": int})


def test_a_leaf_no_fork_mentions_is_left_out() -> None:
    text = render((fork(["<", "x", 10], taken=True),), {"x": int, "y": int})

    assert "y" not in text


def test_a_name_the_leaves_do_not_have_is_an_error() -> None:
    with pytest.raises(ValueError, match="z"):
        render((fork(["<", "z", 10], taken=True),), {"x": int})


def test_a_leaf_of_a_type_nothing_can_declare_is_an_error() -> None:
    with pytest.raises(ValueError, match="str"):
        render((fork(["<", "x", 10], taken=True),), {"x": str})
