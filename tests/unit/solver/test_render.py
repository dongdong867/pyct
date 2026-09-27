import json
from collections.abc import Callable, Mapping

import pytest

from pyct.binding import bind
from pyct.core.branch import Branch, Expression, Site
from pyct.solver.render import program
from pyct.solver.strings import above, below, last_index, occurrences

SITE = Site(file="m.py", line=2, col=7)


def render(prefix: tuple[Branch, ...], leaves: Mapping[str, type]) -> str:
    """The program's text alone, which is what most tests here read."""
    return program(prefix, leaves).text


def fork(expression: Expression, *, taken: bool) -> Branch:
    """A fork at one fixed site: only the condition and the side matter here."""
    return Branch(expression=expression, taken=taken, site=SITE)


def test_a_taken_fork_becomes_a_whole_little_program() -> None:
    text = render((fork(["<", "x", 10], taken=True),), {"x": int})

    assert text.splitlines() == [
        "(set-logic ALL)",
        "(declare-const |arg.x| Int)",
        "(assert (< |arg.x| 10))",
        "(check-sat)",
        "(get-value (|arg.x|))",
    ]


def test_a_fork_the_run_did_not_take_is_asserted_the_other_way() -> None:
    text = render((fork(["<", "x", 10], taken=False),), {"x": int})

    assert "(assert (not (< |arg.x| 10)))" in text.splitlines()


def test_a_negative_number_is_written_as_a_subtraction() -> None:
    text = render((fork(["<", "x", -5], taken=True),), {"x": int})

    assert "(assert (< |arg.x| (- 5)))" in text.splitlines()


def test_the_two_equality_operators_are_written_the_way_smt_spells_them() -> None:
    same = render((fork(["==", "x", 10], taken=True),), {"x": int})
    other = render((fork(["!=", "x", 10], taken=True),), {"x": int})

    assert "(assert (= |arg.x| 10))" in same.splitlines()
    assert "(assert (distinct |arg.x| 10))" in other.splitlines()


def test_arithmetic_is_written_under_its_own_name() -> None:
    text = render((fork([">", ["-", ["*", ["+", "x", 1], 2], 3], 10], taken=True),), {"x": int})

    assert "(assert (> (- (* (+ |arg.x| 1) 2) 3) 10))" in text.splitlines()


def test_a_builtin_and_a_unary_minus_are_written_by_arity() -> None:
    text = render(
        (fork([">", ["abs", "x"], 5], taken=True), fork(["<", ["-", "x"], -3], taken=True)),
        {"x": int},
    )

    assert "(assert (> (abs |arg.x|) 5))" in text.splitlines()
    assert "(assert (< (- |arg.x|) (- 3)))" in text.splitlines()


def test_a_power_is_written_with_a_caret() -> None:
    text = render((fork(["==", ["**", "x", 2], 9], taken=True),), {"x": int})

    assert "(assert (= (^ |arg.x| 2) 9))" in text.splitlines()


def test_floor_division_is_written_as_smts_own_with_the_floor_correction() -> None:
    # SMT-LIB's div is Euclidean, so Python's quotient is one lower exactly when the
    # divisor is negative and something is left over: division-floor-correction-in-render
    text = render((fork(["==", ["//", "x", "y"], 4], taken=True),), {"x": int, "y": int})

    assert (
        "(assert (= (ite (or (> |arg.y| 0) (= (mod |arg.x| |arg.y|) 0))"
        " (div |arg.x| |arg.y|) (- (div |arg.x| |arg.y|) 1)) 4))" in text.splitlines()
    )


def test_modulo_is_written_as_smts_own_shifted_onto_the_divisors_sign() -> None:
    text = render((fork(["==", ["%", "x", "y"], 1], taken=True),), {"x": int, "y": int})

    assert (
        "(assert (= (ite (or (> |arg.y| 0) (= (mod |arg.x| |arg.y|) 0))"
        " (mod |arg.x| |arg.y|) (+ (mod |arg.x| |arg.y|) |arg.y|)) 1))" in text.splitlines()
    )


def test_a_negative_divisor_reaches_the_forms_already_written_as_a_subtraction() -> None:
    quotient = render((fork(["==", ["//", "x", -2], -4], taken=True),), {"x": int})
    remainder = render((fork(["==", ["%", "x", -3], -1], taken=True),), {"x": int})

    # a form joins rendered text, so `-2` arrives spelled the way every other operand is
    assert (
        "(assert (= (ite (or (> (- 2) 0) (= (mod |arg.x| (- 2)) 0))"
        " (div |arg.x| (- 2)) (- (div |arg.x| (- 2)) 1)) (- 4)))" in quotient.splitlines()
    )
    assert (
        "(assert (= (ite (or (> (- 3) 0) (= (mod |arg.x| (- 3)) 0))"
        " (mod |arg.x| (- 3)) (+ (mod |arg.x| (- 3)) (- 3))) (- 1)))" in remainder.splitlines()
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
        "(declare-const |arg.s| String)",
        '(assert (= |arg.s| "abc"))',
        "(check-sat)",
        "(get-value (|arg.s|))",
    ]


def test_a_string_literal_is_written_the_way_cvc5_reads_it() -> None:
    # the expression carries the literal as repr writes it; the program carries SMT-LIB's
    literal = repr('a\nb"c\\d é')

    text = render((fork(["!=", "s", literal], taken=True),), {"s": str})

    assert '(assert (distinct |arg.s| "a\\u{a}b""c\\u{5c}d \\u{e9}"))' in text.splitlines()


def test_a_string_literal_is_not_a_name() -> None:
    # either quote opens a literal: repr picks double quotes for a value holding a single one
    text = render((fork(["==", "s", '"it\'s"'], taken=True),), {"s": str, "t": str})

    assert "(declare-const |arg.s| String)" in text.splitlines()
    assert "declare-const |arg.t|" not in text
    assert '(assert (= |arg.s| "it\'s"))' in text.splitlines()


def test_two_str_leaves_are_compared_as_they_are() -> None:
    text = render((fork(["==", "s", "t"], taken=False),), {"s": str, "t": str})

    assert "(assert (not (= |arg.s| |arg.t|)))" in text.splitlines()


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

    assert f"(assert {written('|arg.s|', 'mn', or_equal=or_equal)})" in text.splitlines()


def test_a_literal_on_the_left_of_an_order_is_written_letter_by_letter_too() -> None:
    text = render((fork(["<", "'mn'", "s"], taken=True),), {"s": str})

    assert f"(assert {above('|arg.s|', 'mn', or_equal=False)})" in text.splitlines()


def test_a_greater_than_on_strings_is_the_same_term_as_the_less_than_it_mirrors() -> None:
    greater = render((fork([">", "s", "t"], taken=True),), {"s": str, "t": str})
    less = render((fork(["<", "t", "s"], taken=True),), {"s": str, "t": str})

    assert "(assert (str.< |arg.t| |arg.s|))" in greater.splitlines()
    assert "(assert (str.< |arg.t| |arg.s|))" in less.splitlines()


def test_an_order_on_two_str_names_is_cvc5s_own() -> None:
    text = render((fork(["<=", "s", "t"], taken=False),), {"s": str, "t": str})

    assert "(assert (not (str.<= |arg.s| |arg.t|)))" in text.splitlines()


def test_an_order_on_ints_is_still_written_as_arithmetic() -> None:
    text = render((fork([">=", "x", "y"], taken=True),), {"x": int, "y": int})

    assert "(assert (>= |arg.x| |arg.y|))" in text.splitlines()


# each search as the expression carries it, and the term the program carries for it
SEARCHES: dict[str, tuple[Expression, str]] = {
    "find": (["find", "s", "'x'"], '(str.indexof |arg.s| "x" 0)'),
    # index answers only on a path where its `in` fork held, so it is find there
    "index": (["index", "s", "'x'"], '(str.indexof |arg.s| "x" 0)'),
    "rfind": (["rfind", "s", "'ab'"], last_index("|arg.s|", '"ab"')),
    # rindex answers only past its `in` fork too, so it is rfind there
    "rindex": (["rindex", "s", "'ab'"], last_index("|arg.s|", '"ab"')),
    "count": (["count", "s", "'ab'"], occurrences("|arg.s|", '"ab"')),
    "count-tracked": (["count", "s", "t"], occurrences("|arg.s|", "|arg.t|")),
}


@pytest.mark.parametrize(("expression", "term"), SEARCHES.values(), ids=list(SEARCHES))
def test_a_search_is_written_as_the_term_that_means_it(expression: Expression, term: str) -> None:
    text = render((fork(["==", expression, 1], taken=True),), {"s": str, "t": str})

    assert f"(assert (= {term} 1))" in text.splitlines()


# each search that answers with a bool, and the term the program asserts for it
SEARCH_TRUTHS: dict[str, tuple[Expression, str]] = {
    # the expression keeps Python's order, needle first; cvc5's contains takes the string first
    "in": (["in", "'x'", "s"], '(str.contains |arg.s| "x")'),
    "in-tracked": (["in", "t", "s"], "(str.contains |arg.s| |arg.t|)"),
    "startswith": (["startswith", "s", "'ab'"], '(str.prefixof "ab" |arg.s|)'),
    "endswith": (["endswith", "s", "'ab'"], '(str.suffixof "ab" |arg.s|)'),
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
        "(declare-const |arg.s| String)",
        "(declare-const |arg.n| Int)",
        '(assert (not (< (str.indexof |arg.s| "x" 0) |arg.n|)))',
        "(check-sat)",
        "(get-value (|arg.s|))",
        "(get-value (|arg.n|))",
    ]


# a value inside an argument, as bind names it and as leaves keys it
PORT: Expression = ["[]", ["[]", "config", "'server'"], "'port'"]
FIRST: Expression = ["[]", "items", 0]
SECOND: Expression = ["[]", "items", 1]


def test_a_value_inside_an_argument_is_declared_under_a_constant_of_its_own() -> None:
    text = render((fork(["<", PORT, 1], taken=True),), {json.dumps(PORT): int})

    assert text.splitlines() == [
        "(set-logic ALL)",
        "(declare-const |leaf.0| Int)",
        "(assert (< |leaf.0| 1))",
        "(check-sat)",
        "(get-value (|leaf.0|))",
    ]


def test_two_values_inside_one_argument_are_two_constants() -> None:
    leaves = {"x": int, json.dumps(FIRST): int, json.dumps(SECOND): int}

    text = render((fork(["==", FIRST, SECOND], taken=False),), leaves)

    lines = text.splitlines()
    assert lines[1:3] == ["(declare-const |leaf.1| Int)", "(declare-const |leaf.2| Int)"]
    assert "(assert (not (= |leaf.1| |leaf.2|)))" in lines


def test_a_str_inside_an_argument_compares_as_a_string() -> None:
    text = render((fork(["==", FIRST, "'x'"], taken=True),), {json.dumps(FIRST): str})

    lines = text.splitlines()
    assert "(declare-const |leaf.0| String)" in lines
    assert '(assert (= |leaf.0| "x"))' in lines
    ordered = render(
        (fork(["<", FIRST, SECOND], taken=True),),
        {
            json.dumps(FIRST): str,
            json.dumps(SECOND): str,
        },
    )
    assert "(assert (str.< |leaf.0| |leaf.1|))" in ordered.splitlines()


def test_an_access_the_seed_does_not_hold_names_its_parameter_in_the_error() -> None:
    # not a leaf, so an operation on items, and items is no leaf either
    with pytest.raises(ValueError, match="items"):
        render((fork(["<", ["[]", "items", 5], 1], taken=True),), {json.dumps(FIRST): int})


def test_a_program_reads_its_answer_back_by_leaf() -> None:
    leaves = {"x": int, "y": int, json.dumps(PORT): int}
    path = (fork([">", ["+", "x", PORT], 1], taken=True),)

    written = program(path, leaves)

    # y is not on the path, so it is neither declared nor read
    assert written.leaves == {"arg.x": "x", "leaf.2": json.dumps(PORT)}
    assert written.read({"arg.x": 3, "leaf.2": 70000}) == {"x": 3, json.dumps(PORT): 70000}


@pytest.mark.parametrize(
    ("name", "constant"),
    [
        pytest.param("div", "|arg.div|", id="a word of the solver's own"),
        pytest.param("café", "|arg.caf%C3%A9|", id="past ascii"),
        # a **kwargs key need not be a name; a quoted symbol cannot hold `|` or a backslash
        pytest.param("a|b\\c", "|leaf.0|", id="not an identifier"),
    ],
)
def test_every_constant_is_quoted_under_pycts_own_prefix(name: str, constant: str) -> None:
    text = render((fork([">", name, 3], taken=True),), {name: int})

    assert f"(declare-const {constant} Int)" in text.splitlines()
    assert f"(assert (> {constant} 3))" in text.splitlines()


def test_an_access_is_a_leaf_by_the_steps_binding_takes(monkeypatch: pytest.MonkeyPatch) -> None:
    # an attribute is a step binding may take next; the solver follows with no change of its own
    monkeypatch.setattr(bind, "_STEPS", frozenset({"[]", "getattr"}))
    limit: Expression = ["getattr", "rule", "'limit'"]

    text = render((fork([">", limit, 100], taken=True),), {json.dumps(limit): int})

    assert "(declare-const |leaf.0| Int)" in text.splitlines()
    assert "(assert (> |leaf.0| 100))" in text.splitlines()
