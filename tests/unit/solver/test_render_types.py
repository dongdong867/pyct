"""Each head render writes says the type of its value, so a head above it picks its operator."""

import pytest

from pyct.core.branch import Expression
from pyct.solver.heads import FORMS, OPERATORS, POSITIONED, RESULTS, STRING_ORDERS
from tests.unit.solver.test_render import fork, render


def test_every_head_render_writes_says_what_type_its_value_is() -> None:
    written = {head for head, _ in OPERATORS} | {head for head, _ in FORMS}
    written |= set(POSITIONED) | set(STRING_ORDERS)

    # a head with no entry cannot say whether a `+` or an order above it is on strings, and a
    # wrong guess is a program cvc5 refuses, which stops the run on `solver failed`
    assert written - set(RESULTS) == set()


# a term each head builds, grouped by the type of its value in Python: `+` builds an int from
# ints, a float from floats and a str from strs
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
FLOAT_TERMS: list[Expression] = [
    ["+", "f", 1.5],
    ["-", "f", 1.5],
    ["-", "f"],
    ["*", "f", 2.0],
    ["/", "f", 2.0],
    ["abs", "f"],
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
    ["is_integer", "f"],
    *([op, ["<", "x", 1], ["<", "n", 1]] for op in ("&", "|", "^")),
]
TYPED_LEAVES: dict[str, type] = {"x": int, "n": int, "f": float, "g": float, "s": str, "t": str}


def _head(term: Expression) -> str:
    assert isinstance(term, list) and isinstance(term[0], str), term
    return term[0]


def _ids(terms: list[Expression]) -> list[str]:
    """A test id per term: its head, and how many operands it has, so `-` reads apart."""
    return [f"{_head(term)}/{len(term) - 1}" for term in terms if isinstance(term, list)]


def _asserted(text: str) -> str:
    """The one assertion a one-fork program holds."""
    return next(line for line in text.splitlines() if line.startswith("(assert "))


def test_every_head_in_the_table_has_a_term_of_its_type_here() -> None:
    terms = INT_TERMS + FLOAT_TERMS + STR_TERMS + BOOL_TERMS
    assert {_head(term) for term in terms} == set(RESULTS)


@pytest.mark.parametrize("term", INT_TERMS, ids=_ids(INT_TERMS))
def test_a_head_that_builds_an_int_is_ordered_as_an_int(term: Expression) -> None:
    text = render((fork(["<", term, "n"], taken=True),), TYPED_LEAVES)

    assert _asserted(text).startswith("(assert (< ")


@pytest.mark.parametrize("term", FLOAT_TERMS, ids=_ids(FLOAT_TERMS))
def test_a_head_that_builds_a_float_is_ordered_as_a_float(term: Expression) -> None:
    text = render((fork(["<", term, "g"], taken=True),), TYPED_LEAVES)

    assert _asserted(text).startswith("(assert (fp.lt ")


@pytest.mark.parametrize("term", STR_TERMS, ids=_ids(STR_TERMS))
def test_a_head_that_builds_a_str_is_ordered_as_a_str(term: Expression) -> None:
    text = render((fork(["<", term, "t"], taken=True),), TYPED_LEAVES)

    assert _asserted(text).startswith("(assert (str.< ")
