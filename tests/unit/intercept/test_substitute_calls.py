"""Which calls and operators the transform substitutes, and what it leaves as written."""

import ast

import pytest

from pyct.intercept.substitute import substitute
from tests.unit.intercept.test_substitute import substituted


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("int(x)", "__pyct_call__(int)(x)"),
        ("float(x)", "__pyct_call__(float)(x)"),
        ("bool(x)", "__pyct_call__(bool)(x)"),
        ("int(s, 16)", "__pyct_call__(int)(s, 16)"),
        ("int(s, base=2)", "__pyct_call__(int)(s, base=2)"),
        ("builtins.int(x)", "__pyct_call__(builtins.int)(x)"),
        ("map(int, parts)", "__pyct_call__(map)(int, parts)"),
        ("map(builtins.float, parts)", "__pyct_call__(map)(builtins.float, parts)"),
        # a `math` function, after a dot or bare as `from math import sqrt` binds it
        ("math.sqrt(x)", "__pyct_call__(math.sqrt)(x)"),
        ("sqrt(x)", "__pyct_call__(sqrt)(x)"),
        ("math.isclose(x, 0.1, rel_tol=t)", "__pyct_call__(math.isclose)(x, 0.1, rel_tol=t)"),
        ("math.gcd(n, 6)", "__pyct_call__(math.gcd)(n, 6)"),
        ("logger.log(x)", "__pyct_call__(logger.log)(x)"),
        ('"abc".find(s)', "__pyct_method__('abc'.find, s)"),
        ("'abc'.startswith(s, 1)", "__pyct_method__('abc'.startswith, s, 1)"),
        ("','.split(sep=s)", "__pyct_method__(','.split, sep=s)"),
        ("','.join(parts)", "__pyct_method__(','.join, parts)"),
    ],
)
def test_each_call_becomes_a_call_of_its_router(source: str, expected: str) -> None:
    assert substituted(source) == expected


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("0.5 + n", "0.5 + __pyct_handed__(n, 0.5)"),
        ("2.5 < n", "2.5 < __pyct_handed__(n, 2.5)"),
        ("1.0 / n", "1.0 / __pyct_handed__(n, 1.0)"),
        ("True + n", "True + __pyct_handed__(n, True)"),
        ("True == n", "True == __pyct_handed__(n, True)"),
        ("True & (n > 0)", "True & __pyct_handed__(n > 0, True)"),
        ("-0.5 ** n", "-0.5 ** __pyct_handed__(n, 0.5)"),
        ("(-0.5) ** n", "(-0.5) ** __pyct_handed__(n, -0.5)"),
        ("(1.0 + 2.0) - n", "1.0 + 2.0 - __pyct_handed__(n, 3.0)"),
        ("False != f(x) + 1", "False != __pyct_handed__(f(x) + 1, False)"),
        ("0.5 * (2.5 * n)", "0.5 * __pyct_handed__(2.5 * __pyct_handed__(n, 2.5), 0.5)"),
    ],
)
def test_an_operator_with_a_float_or_bool_literal_on_the_left_hands_its_right_side_over(
    source: str, expected: str
) -> None:
    assert substituted(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        # a right side that is never tracked: a constant, one CPython folds, or a display
        "0.5 + 1",
        "True == 'a'",
        "0.5 * (2 + 3)",
        "0.5 + [b]",
        "True + (b, c)",
        "0.5 + f'{b}'",
        # a left side that is no float or bool literal, however it is written
        "1 + n",
        "'a' + s",
        "'x' * n",
        "None == n",
        "a + b",
        "x * y - z",
        "RATE * n",
        "s + t",
        "a < b",
        "(1 + 2) * n",
        # an operator with no number to hand over, a chained compare, and an assignment's
        "0.5 @ b",
        "0.5 < b < c",
        "t += n",
        # a call whose arguments are not written out, or that has none
        "int(*args)",
        "float(**kwargs)",
        "'abc'.find(*args)",
        "'{}'.format(**values)",
        "int()",
        "'abc'.strip()",
        # a callee spelled otherwise, a receiver that is no str literal, and a dunder
        "conv(x)",
        "map(str, parts)",
        "map(f, parts)",
        # the roundings `math` asks the number itself for, and a `math` name called with nothing
        "math.floor(x)",
        "ceil(x)",
        "math.trunc(x)",
        "math.sqrt(*args)",
        "text.find(s)",
        "items.index(x)",
        "b'abc'.find(s)",
        "f'{a}'.find(s)",
        "'abc'.__contains__(s)",
        # a method call whose name sits on a later line than the call starts
        "('abc'\n    .find(s))",
        "(builtins\n    .int(x))",
    ],
)
def test_other_calls_and_operators_are_left_as_written(source: str) -> None:
    assert substituted(source) == ast.unparse(ast.parse(source))


def test_a_call_with_more_arguments_than_it_takes_written_out_is_left_as_written() -> None:
    source = f"'{{}}'.format({', '.join(f'a{n}' for n in range(21))})"

    assert substituted(source) == ast.unparse(ast.parse(source))


def test_the_callee_and_the_operands_are_the_operation_s_own_nodes() -> None:
    tree = ast.parse("y = int(x) + 'abc'.find(s) + (0.5 + n)")
    total = tree.body[0].value  # pyrefly: ignore[missing-attribute]
    call_node, method_node = total.left.left, total.left.right
    callee, receiver, right = call_node.func, method_node.func, total.right.right

    body = substitute(tree).body
    rebuilt = body[1].value  # pyrefly: ignore[missing-attribute]

    assert rebuilt.left.left.func.args[0] is callee
    assert rebuilt.left.right.args[0] is receiver
    assert rebuilt.right.right.args[0] is right


def test_a_call_takes_the_call_s_position_and_its_name_the_callee_s() -> None:
    body = substitute(ast.parse("y = (\n    int(\n        x))\n")).body
    call = body[1].value  # pyrefly: ignore[missing-attribute]

    assert (call.lineno, call.col_offset) == (2, 4)
    assert (call.func.lineno, call.func.col_offset) == (2, 4)
    assert (call.func.func.lineno, call.func.func.col_offset) == (2, 4)


def test_a_handed_right_side_sits_where_the_literal_does() -> None:
    body = substitute(ast.parse("y = (0.5 +\n    n)\n")).body
    handed = body[1].value.right  # pyrefly: ignore[missing-attribute]

    assert (handed.lineno, handed.col_offset) == (1, 5)
    assert (handed.func.lineno, handed.args[1].lineno) == (1, 1)
    assert handed.args[0].lineno == 2
