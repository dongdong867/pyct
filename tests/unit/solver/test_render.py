from collections.abc import Callable, Mapping

import pytest

from pyct.core.branch import Branch, Expression, Site
from pyct.solver.render import FORMS, OPERATORS, POSITIONED, RESULTS, STRING_ORDERS, program
from pyct.solver.strings import (
    above,
    below,
    character,
    last_index,
    occurrences,
    replaced,
    sliced,
    without_prefix,
    without_suffix,
)

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


def test_an_operation_with_a_number_on_its_left_is_written_on_ints() -> None:
    # core writes `10 - x` as the reflected subtraction, the number first
    text = render((fork(["==", ["-", 10, "x"], 3], taken=True),), {"x": int})

    assert "(assert (= (- 10 |arg.x|) 3))" in text.splitlines()


def test_an_operator_nothing_encodes_is_an_error() -> None:
    with pytest.raises(ValueError, match="<<"):
        render((fork(["<<", "x", 1], taken=True),), {"x": int})


def test_an_operator_nothing_encodes_is_an_error_where_it_is_held_twice() -> None:
    part: Expression = ["<<", "x", 1]

    # a part held twice is defined once, but one of no type is written out, naming its gap
    with pytest.raises(ValueError, match="<< on int"):
        render((fork(["==", part, part], taken=True),), {"x": int})


def test_a_head_that_is_no_name_is_an_error() -> None:
    with pytest.raises(ValueError, match="cannot render 7"):
        render((fork([7, "x"], taken=True),), {"x": int})


def test_a_leaf_no_fork_mentions_is_left_out() -> None:
    text = render((fork(["<", "x", 10], taken=True),), {"x": int, "y": int})

    assert "y" not in text


def test_a_name_the_leaves_do_not_have_is_an_error() -> None:
    with pytest.raises(ValueError, match="z"):
        render((fork(["<", "z", 10], taken=True),), {"x": int})


def test_a_leaf_of_a_type_nothing_can_declare_is_an_error() -> None:
    with pytest.raises(ValueError, match="cannot declare x: nothing solves a float"):
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


# the constants the program declares for the parameters s, t and x
S, T, X = "|arg.s|", "|arg.t|", "|arg.x|"

# each piece as the expression carries it, and the term the program carries for it
PIECES: dict[str, tuple[Expression, str]] = {
    "index": (["[]", "s", 0], character(S, 0)),
    # a negative index reaches its form as the number it is, not a subtraction already written
    "negative-index": (["[]", "s", -1], character(S, -1)),
    "slice": (["[:]", "s", 1, 3], sliced(S, 1, 3)),
    "slice-missing-stop": (["[:]", "s", 2, None], sliced(S, 2, None)),
    "slice-missing-start": (["[:]", "s", None, -1], sliced(S, None, -1)),
    "plus": (["+", "s", "t"], f"(str.++ {S} {T})"),
    "plus-literal-first": (["+", "'x'", "s"], f'(str.++ "x" {S})'),
    "replace": (["replace", "s", "'a'", "t"], replaced(S, '"a"', T)),
    "removeprefix": (["removeprefix", "s", "'x'"], without_prefix(S, '"x"')),
    "removesuffix": (["removesuffix", "s", "t"], without_suffix(S, T)),
    # the piece the index reads is defined once and read by its name
    "piece-of-a-piece": (["[]", ["[:]", "s", 1, None], 0], character("e!0", 0)),
}


@pytest.mark.parametrize(("expression", "term"), PIECES.values(), ids=list(PIECES))
def test_a_piece_is_written_as_the_term_that_means_it(expression: Expression, term: str) -> None:
    text = render((fork(["==", expression, "'ab'"], taken=True),), {"s": str, "t": str})

    assert f'(assert (= {term} "ab"))' in text.splitlines()


def test_the_length_of_a_string_is_cvc5s_own() -> None:
    text = render((fork([">", ["len", "s"], 3], taken=False),), {"s": str})

    assert f"(assert (not (> (str.len {S}) 3)))" in text.splitlines()


def test_a_plus_on_ints_stays_arithmetic_beside_a_plus_on_strings() -> None:
    text = render(
        (
            fork(["==", ["+", "s", "'a'"], "'ba'"], taken=True),
            fork(["<", ["+", "x", 1], 3], taken=True),
        ),
        {"s": str, "x": int},
    )

    assert f'(assert (= (str.++ {S} "a") "ba"))' in text.splitlines()
    assert f"(assert (< (+ {X} 1) 3))" in text.splitlines()


def test_an_order_on_two_pieces_is_cvc5s_own() -> None:
    # neither side is a literal or a name, so the heads alone say both sides are strings
    text = render(
        (fork([">=", ["[]", "s", 0], ["+", "t", "t"]], taken=True),), {"s": str, "t": str}
    ).splitlines()

    assert f"(define-fun e!0 () String {character(S, 0)})" in text
    assert f"(define-fun e!1 () String (str.++ {T} {T}))" in text
    assert "(assert (str.<= e!1 e!0))" in text


def test_a_plus_on_two_pieces_joins_strings() -> None:
    # `s.replace("a", "b") + s.removeprefix("x") == "bb"`: no name and no literal on the `+`
    joined: Expression = ["+", ["replace", "s", "'a'", "'b'"], ["removeprefix", "s", "'x'"]]

    text = render((fork(["==", joined, "'bb'"], taken=True),), {"s": str})

    both = f"{replaced(S, '"a"', '"b"')} {without_prefix(S, '"x"')}"
    assert f'(assert (= (str.++ {both}) "bb"))' in text.splitlines()


@pytest.mark.parametrize("head", ["removeprefix", "removesuffix"])
def test_a_piece_given_a_piece_defines_each_once(head: str) -> None:
    string, affix = sliced(S, 1, None), sliced(T, 1, None)

    text = render(
        (fork(["==", [head, ["[:]", "s", 1, None], ["[:]", "t", 1, None]], "'x'"], taken=True),),
        {"s": str, "t": str},
    )

    # the form reads both its string and what it removes more than once; each is defined once
    # and read by its name
    lines = text.splitlines()
    assert f"(define-fun e!0 () String {string})" in lines
    assert f"(define-fun e!1 () String {affix})" in lines
    assert f'(assert (= {FORMS[head]("e!0", "e!1")} "x"))' in lines
    assert (text.count(string), text.count(affix)) == (1, 1)


def test_every_head_render_writes_says_what_type_its_value_is() -> None:
    written = {head for head, _ in OPERATORS} | set(FORMS) | set(POSITIONED) | set(STRING_ORDERS)

    # a head with no entry cannot say whether a `+` or an order above it is on strings, and a
    # wrong guess is a program cvc5 refuses, which stops the run on `solver failed`
    assert written - set(RESULTS) == set()


# a term each head builds, grouped by the type of its value in Python: `+` builds an int from
# ints and a str from strs
INT_TERMS: list[Expression] = [
    ["+", "x", 1],
    ["-", "x", 1],
    ["*", "x", 2],
    ["**", "x", 2],
    ["abs", "x"],
    ["//", "x", 2],
    ["%", "x", 2],
    ["find", "s", "'a'"],
    ["rfind", "s", "'a'"],
    ["index", "s", "'a'"],
    ["rindex", "s", "'a'"],
    ["count", "s", "'a'"],
    ["len", "s"],
]
STR_TERMS: list[Expression] = [
    ["+", "s", "'a'"],
    ["[]", "s", 0],
    ["[:]", "s", 1, None],
    ["replace", "s", "'a'", "'b'"],
    ["removeprefix", "s", "'a'"],
    ["removesuffix", "s", "'a'"],
]
BOOL_TERMS: list[Expression] = [[op, "x", 1] for op in ("<", "<=", ">", ">=", "==", "!=")] + [
    ["in", "'a'", "s"],
    ["startswith", "s", "'a'"],
    ["endswith", "s", "'a'"],
    *([op, ["<", "x", 1], ["<", "n", 1]] for op in ("&", "|", "^")),
]
TYPED_LEAVES: dict[str, type] = {"x": int, "n": int, "s": str, "t": str}


def _head(term: Expression) -> str:
    assert isinstance(term, list) and isinstance(term[0], str), term
    return term[0]


def _asserted(text: str) -> str:
    """The one assertion a one-fork program holds."""
    return next(line for line in text.splitlines() if line.startswith("(assert "))


def test_every_head_in_the_table_has_a_term_of_its_type_here() -> None:
    assert {_head(term) for term in INT_TERMS + STR_TERMS + BOOL_TERMS} == set(RESULTS)


@pytest.mark.parametrize("term", INT_TERMS, ids=[_head(term) for term in INT_TERMS])
def test_a_head_that_builds_an_int_is_ordered_as_an_int(term: Expression) -> None:
    text = render((fork(["<", term, "n"], taken=True),), TYPED_LEAVES)

    assert _asserted(text).startswith("(assert (< ")


@pytest.mark.parametrize("term", STR_TERMS, ids=[_head(term) for term in STR_TERMS])
def test_a_head_that_builds_a_str_is_ordered_as_a_str(term: Expression) -> None:
    text = render((fork(["<", term, "t"], taken=True),), TYPED_LEAVES)

    assert _asserted(text).startswith("(assert (str.< ")


def test_a_position_that_is_not_a_plain_int_is_an_error() -> None:
    with pytest.raises(ValueError, match="position"):
        render((fork(["==", ["[]", "s", "n"], "'a'"], taken=True),), {"s": str, "n": int})


def test_a_missing_bound_outside_a_slice_is_an_error() -> None:
    with pytest.raises(ValueError, match="missing bound"):
        render((fork(["==", "s", None], taken=True),), {"s": str})


# a piece a loop takes of its own string on every pass, `s = s[1:]` and the like
NESTINGS: dict[str, Callable[[Expression], Expression]] = {
    "s = s[1:]": lambda term: ["[:]", term, 1, None],
    "s = s[-3:-1]": lambda term: ["[:]", term, -3, -1],
    "s = s[-1]": lambda term: ["[]", term, -1],
    "s = s.removeprefix(' ')": lambda term: ["removeprefix", term, "' '"],
    "s = s.removesuffix(t)": lambda term: ["removesuffix", term, "t"],
}


def _nested(nest: Callable[[Expression], Expression], depth: int) -> str:
    """One fork on a piece nested ``depth`` passes deep, as the program writes it."""
    term: Expression = "s"
    for _ in range(depth):
        term = nest(term)
    return render((fork(["!=", term, "''"], taken=True),), {"s": str, "t": str})


@pytest.mark.parametrize("nest", NESTINGS.values(), ids=list(NESTINGS))
def test_a_piece_nested_thirty_deep_grows_the_program_by_one_level_at_a_time(
    nest: Callable[[Expression], Expression],
) -> None:
    sizes = [len(_nested(nest, depth)) for depth in (28, 29, 30)]

    # each form names its string once, so a pass adds the same text whatever lies below it,
    # where writing the string out at every use doubles the text or more with each pass
    assert sizes[2] - sizes[1] == sizes[1] - sizes[0]
    assert sizes[2] < 30 * 200
