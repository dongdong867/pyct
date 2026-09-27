"""Which compares the transform substitutes, what it leaves alone, and what each call is handed."""

import ast

import pytest

from pyct.intercept.substitute import BOUND, WRITTEN_MOST, substitute


def substituted(source: str) -> str:
    """The source as the transform leaves it, written back as Python."""
    return ast.unparse(substitute(ast.parse(source)))


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a is True", "__pyct_is__(a, True)"),
        ("a is not False", "__pyct_is_not__(a, False)"),
        ("True is a", "__pyct_is__(True, a)"),
        ("a in b", "__pyct_in__(a, b)"),
        ("a not in b", "__pyct_not_in__(a, b)"),
        # `not` folds into the operator, as CPython's optimizer folds it
        ("not (a in b)", "__pyct_not_in__(a, b)"),
        ("not a in b", "__pyct_not_in__(a, b)"),
        ("not not (a in b)", "__pyct_in__(a, b)"),
        ("not (a is True)", "__pyct_is_not__(a, True)"),
        ("not (a is not False)", "__pyct_is__(a, False)"),
    ],
)
def test_each_shape_becomes_a_call_of_its_function(source: str, expected: str) -> None:
    assert substituted(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        # `is` with anything but the constants True and False, a value equal to one included
        "a is None",
        "a is 1",
        "not (a is None)",
        # a chained compare, and every other operator
        "0 < x in {1, 5}",
        "a == b",
        "not (a == b)",
        # a loop, a comprehension and a pattern hold `in` or `is` but no compare
        "for x in xs:\n    pass",
        "[x for x in xs]",
        "match v:\n    case True:\n        pass",
        # annotations, which Python may keep as text
        "def f(x: a in b) -> a is True:\n    y: a in b = 1",
    ],
)
def test_other_code_is_left_as_written(source: str) -> None:
    assert substituted(source) == ast.unparse(ast.parse(source))


def test_a_compare_inside_an_operand_is_substituted_too() -> None:
    assert substituted("(a in b) is True") == "__pyct_is__(__pyct_in__(a, b), True)"
    assert substituted("f(x in {k: v in w})") == "f(__pyct_in__(x, {k: __pyct_in__(v, w)}))"


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # a list is a tuple beside `in`, and one of constants a tuple constant
        ("x in [a, b]", "__pyct_in__(x, (a, b))"),
        ("x in [1, -2, (3, 4)]", "__pyct_in__(x, (1, -2, (3, 4)))"),
        ("x in [*a, b]", "__pyct_in__(x, [*a, b])"),
        # a set of constants is a frozenset constant, handed its elements in the order written
        ("x in {5, 1}", "__pyct_in__(x, frozenset({1, 5}), (5, 1))"),
        ("x in {a, 1}", "__pyct_in__(x, {a, 1})"),
        # a dict display stays as written, handed its constant keys in the order written
        ("x in {'b': f(), 'a': 2}", "__pyct_in__(x, {'b': f(), 'a': 2}, ('b', 'a'))"),
        ("x in {k: 1}", "__pyct_in__(x, {k: 1})"),
        ("x in {**d, 'a': 1}", "__pyct_in__(x, {**d, 'a': 1})"),
        ("x in {}", "__pyct_in__(x, {}, ())"),
        ("x in (1, 2)", "__pyct_in__(x, (1, 2))"),
        ("x in s", "__pyct_in__(x, s)"),
    ],
)
def test_a_container_is_handed_over_as_cpython_compiles_it_beside_in(
    source: str, expected: str
) -> None:
    assert substituted(source) == expected


def test_a_larger_display_hands_over_no_elements() -> None:
    elements = ", ".join(str(n) for n in range(WRITTEN_MOST + 1))
    call = substitute(ast.parse(f"x in {{{elements}}}")).body[0]

    assert isinstance(call, ast.Expr) and isinstance(call.value, ast.Call)
    assert len(call.value.args) == 2


def test_an_element_that_cannot_stand_alone_is_no_constant() -> None:
    source = "async def f():\n    return x in [await g(), 1]"
    assert "__pyct_in__(x, (await g(), 1))" in substituted(source)


def test_a_deeply_nested_expression_needs_no_deep_stack() -> None:
    # a chain of 5,000 `+` over as many lines, which the walk and the search for the first
    # instruction each go down one step at a time
    chain = " +\n".join(["a"] * 5000)
    tree = substitute(ast.parse(f"({chain}) in b"))
    call = tree.body[0].value  # pyrefly: ignore[missing-attribute]

    assert isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    assert (call.func.id, call.func.lineno) == ("__pyct_in__", 1)


def test_each_call_takes_the_compare_s_position_and_its_name_the_first_operand_s_line() -> None:
    tree = substitute(ast.parse("if (\n    a).b in c:\n    pass"))
    test = tree.body[0].test  # pyrefly: ignore[missing-attribute]

    assert (test.lineno, test.col_offset, test.end_lineno) == (1, 3, 2)
    assert (test.func.lineno, test.func.end_lineno) == (2, 2)


def test_the_bound_names_are_dunders_that_name_the_core_functions() -> None:
    assert all(name.startswith("__") and name.endswith("__") for name in BOUND)
    assert set(BOUND.values()) == {"is_", "is_not", "in_", "not_in"}
