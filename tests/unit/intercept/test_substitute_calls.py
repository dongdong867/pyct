"""Which calls and operators the transform substitutes, and what it leaves as written."""

import ast

import pytest

from pyct.intercept.substitute import substitute
from tests.unit.intercept.test_substitute import substituted


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("int(x)", "__pyct_call__(int, x)"),
        ("float(x)", "__pyct_call__(float, x)"),
        ("bool(x)", "__pyct_call__(bool, x)"),
        ("int(s, 16)", "__pyct_call__(int, s, 16)"),
        ("int(s, base=2)", "__pyct_call__(int, s, base=2)"),
        ("builtins.int(x)", "__pyct_call__(builtins.int, x)"),
        ("map(int, parts)", "__pyct_call__(map, int, parts)"),
        ("map(builtins.float, parts)", "__pyct_call__(map, builtins.float, parts)"),
        ('"abc".find(s)', "__pyct_method__('abc'.find, s)"),
        ("text.startswith(s, 1)", "__pyct_method__(text.startswith, s, 1)"),
        ("a.b.split(sep=s)", "__pyct_method__(a.b.split, sep=s)"),
        # a name nothing tells from a str's own until the call runs
        ("items.index(x)", "__pyct_method__(items.index, x)"),
    ],
)
def test_each_call_becomes_a_call_of_its_router_with_the_callee_first(
    source: str, expected: str
) -> None:
    assert substituted(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("0.5 + n", "__pyct_add__(0.5, n)"),
        ("2.5 < n", "__pyct_lt__(2.5, n)"),
        ("1.0 / n", "__pyct_truediv__(1.0, n)"),
        ("RATE * n", "__pyct_mul__(RATE, n)"),
        ("True + n", "__pyct_add__(True, n)"),
        ("True == n", "__pyct_eq__(True, n)"),
        ("True & (n > 0)", "__pyct_and__(True, n > 0)"),
        ("-0.5 ** n", "-__pyct_pow__(0.5, n)"),
        ("(1.0 + 2.0) - n", "__pyct_sub__(1.0 + 2.0, n)"),
        ("a % b", "__pyct_mod__(a, b)"),
        ("a // b >= c", "__pyct_ge__(__pyct_floordiv__(a, b), c)"),
        ("a << b | c ^ d", "__pyct_or__(__pyct_lshift__(a, b), __pyct_xor__(c, d))"),
        ("a >> b != c", "__pyct_ne__(__pyct_rshift__(a, b), c)"),
        ("a <= b", "__pyct_le__(a, b)"),
    ],
)
def test_an_operator_a_plain_number_may_hand_over_becomes_a_call(
    source: str, expected: str
) -> None:
    assert substituted(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        # a right side that is never tracked: a constant, one CPython folds, or a display
        "n + 1",
        "x == 'a'",
        "n * (2 + 3)",
        "a + [b]",
        "a + (b, c)",
        "a + f'{b}'",
        # a left side that is never a plain float or bool
        "1 + n",
        "'a' + s",
        "[a] + b",
        "(1 + 2) * n",
        "{a: b} | c",
        # an operator with no number to hand over, and a chained compare
        "a @ b",
        "a < b < c",
        # a call whose arguments are not written out, or that has none
        "int(*args)",
        "float(**kwargs)",
        "text.find(*args)",
        "text.format(**values)",
        "int()",
        "text.strip()",
        # a callee spelled otherwise, a method str does not have, and a dunder
        "conv(x)",
        "map(str, parts)",
        "map(f, parts)",
        "items.append(x)",
        "text.__contains__(s)",
        # a method call whose name sits on a later line than the call starts
        "(text\n    .find(s))",
        "(builtins\n    .int(x))",
    ],
)
def test_other_calls_and_operators_are_left_as_written(source: str) -> None:
    assert substituted(source) == ast.unparse(ast.parse(source))


def test_a_call_with_more_arguments_than_it_takes_written_out_is_left_as_written() -> None:
    source = f"text.format({', '.join(f'a{n}' for n in range(21))})"

    assert substituted(source) == ast.unparse(ast.parse(source))


def test_the_callee_and_the_operands_are_the_operation_s_own_nodes() -> None:
    tree = ast.parse("y = int(x) + text.find(s)")
    call_node, method_node = tree.body[0].value.left, tree.body[0].value.right  # pyrefly: ignore
    callee, receiver = call_node.func, method_node.func

    body = substitute(tree).body
    added = body[1].value  # pyrefly: ignore[missing-attribute]

    assert added.func.id == "__pyct_add__"
    assert added.args[0].args[0] is callee
    assert added.args[1].args[0] is receiver


def test_a_call_takes_the_call_s_position_and_its_name_the_callee_s() -> None:
    body = substitute(ast.parse("y = (\n    int(\n        x))\n")).body
    call = body[1].value  # pyrefly: ignore[missing-attribute]

    assert (call.lineno, call.col_offset) == (2, 4)
    assert (call.func.lineno, call.func.col_offset) == (2, 4)
