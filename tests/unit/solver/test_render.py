from collections.abc import Callable

import pytest

from pyct.core.branch import Branch, Expression, Site
from pyct.solver.render import render
from pyct.solver.strings import above, below, last_index, occurrences

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
    with pytest.raises(ValueError, match="float"):
        render((fork(["<", "x", 10], taken=True),), {"x": float})


def test_a_str_leaf_is_declared_a_string() -> None:
    text = render((fork(["==", "s", "'abc'"], taken=True),), {"s": str})

    assert text.splitlines() == [
        "(set-logic ALL)",
        "(declare-const s String)",
        '(assert (= s "abc"))',
        "(check-sat)",
        "(get-value (s))",
    ]


def test_a_string_literal_is_written_the_way_cvc5_reads_it() -> None:
    # the expression carries the literal as repr writes it; the program carries SMT-LIB's
    literal = repr('a\nb"c\\d é')

    text = render((fork(["!=", "s", literal], taken=True),), {"s": str})

    assert '(assert (distinct s "a\\u{a}b""c\\u{5c}d \\u{e9}"))' in text.splitlines()


def test_a_string_literal_is_not_a_name() -> None:
    # either quote opens a literal: repr picks double quotes for a value holding a single one
    text = render((fork(["==", "s", '"it\'s"'], taken=True),), {"s": str, "t": str})

    assert "(declare-const s String)" in text.splitlines()
    assert "declare-const t" not in text
    assert '(assert (= s "it\'s"))' in text.splitlines()


def test_two_str_leaves_are_compared_as_they_are() -> None:
    text = render((fork(["==", "s", "t"], taken=False),), {"s": str, "t": str})

    assert "(assert (not (= s t)))" in text.splitlines()


# an order against a literal, and the side of it strings.py writes: `>` and `>=` swap, so the
# term sits above the literal
ORDERS_AGAINST_A_LITERAL: dict[str, tuple[Callable[..., str], bool]] = {
    "<": (below, False),
    "<=": (below, True),
    ">": (above, False),
    ">=": (above, True),
}


@pytest.mark.parametrize(
    ("op", "side"), ORDERS_AGAINST_A_LITERAL.items(), ids=list(ORDERS_AGAINST_A_LITERAL)
)
def test_an_order_against_a_literal_is_written_letter_by_letter(
    op: str, side: tuple[Callable[..., str], bool]
) -> None:
    written, or_equal = side
    text = render((fork([op, "s", "'mn'"], taken=True),), {"s": str})

    assert f"(assert {written('s', 'mn', or_equal=or_equal)})" in text.splitlines()


def test_a_literal_on_the_left_of_an_order_is_written_letter_by_letter_too() -> None:
    text = render((fork(["<", "'mn'", "s"], taken=True),), {"s": str})

    assert f"(assert {above('s', 'mn', or_equal=False)})" in text.splitlines()


def test_a_greater_than_on_strings_is_the_same_term_as_the_less_than_it_mirrors() -> None:
    greater = render((fork([">", "s", "t"], taken=True),), {"s": str, "t": str})
    less = render((fork(["<", "t", "s"], taken=True),), {"s": str, "t": str})

    assert "(assert (str.< t s))" in greater.splitlines()
    assert "(assert (str.< t s))" in less.splitlines()


def test_an_order_on_two_str_names_is_cvc5s_own() -> None:
    text = render((fork(["<=", "s", "t"], taken=False),), {"s": str, "t": str})

    assert "(assert (not (str.<= s t)))" in text.splitlines()


def test_an_order_on_ints_is_still_written_as_arithmetic() -> None:
    text = render((fork([">=", "x", "y"], taken=True),), {"x": int, "y": int})

    assert "(assert (>= x y))" in text.splitlines()


# each search as the expression carries it, and the term the program carries for it
SEARCHES: dict[str, tuple[Expression, str]] = {
    "find": (["find", "s", "'x'"], '(str.indexof s "x" 0)'),
    # index answers only on a path where its `in` fork held, so it is find there
    "index": (["index", "s", "'x'"], '(str.indexof s "x" 0)'),
    "rfind": (["rfind", "s", "'ab'"], last_index("s", '"ab"')),
    # rindex answers only past its `in` fork too, so it is rfind there
    "rindex": (["rindex", "s", "'ab'"], last_index("s", '"ab"')),
    "count": (["count", "s", "'ab'"], occurrences("s", '"ab"')),
    "count-tracked": (["count", "s", "t"], occurrences("s", "t")),
}


@pytest.mark.parametrize(("expression", "term"), SEARCHES.values(), ids=list(SEARCHES))
def test_a_search_is_written_as_the_term_that_means_it(expression: Expression, term: str) -> None:
    text = render((fork(["==", expression, 1], taken=True),), {"s": str, "t": str})

    assert f"(assert (= {term} 1))" in text.splitlines()


# each search that answers with a bool, and the term the program asserts for it
SEARCH_TRUTHS: dict[str, tuple[Expression, str]] = {
    # the expression keeps Python's order, needle first; cvc5's contains takes the string first
    "in": (["in", "'x'", "s"], '(str.contains s "x")'),
    "in-tracked": (["in", "t", "s"], "(str.contains s t)"),
    "startswith": (["startswith", "s", "'ab'"], '(str.prefixof "ab" s)'),
    "endswith": (["endswith", "s", "'ab'"], '(str.suffixof "ab" s)'),
}


@pytest.mark.parametrize(("expression", "term"), SEARCH_TRUTHS.values(), ids=list(SEARCH_TRUTHS))
def test_a_search_that_answers_with_a_bool_is_asserted_as_its_term(
    expression: Expression, term: str
) -> None:
    text = render((fork(expression, taken=False),), {"s": str, "t": str})

    assert f"(assert (not {term}))" in text.splitlines()


def test_a_search_answer_compared_with_an_int_declares_both_leaves() -> None:
    text = render((fork(["<", ["find", "s", "'x'"], "n"], taken=False),), {"s": str, "n": int})

    assert text.splitlines() == [
        "(set-logic ALL)",
        "(declare-const s String)",
        "(declare-const n Int)",
        '(assert (not (< (str.indexof s "x" 0) n)))',
        "(check-sat)",
        "(get-value (s))",
        "(get-value (n))",
    ]
