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
        ("type(x)", "__pyct_call__(type)(x)"),
        ("type(x > 0) is bool", "__pyct_call__(type)(x > 0) is bool"),
        ("builtins.type(x)", "__pyct_call__(builtins.type)(x)"),
        ("range(n)", "__pyct_call__(range)(n)"),
        ("range(a, b, -1)", "__pyct_call__(range)(a, b, -1)"),
        ("builtins.range(n)", "__pyct_call__(builtins.range)(n)"),
        ("range(n, 10)", "__pyct_call__(range)(n, 10)"),
        ("range(3, n.stop)", "__pyct_call__(range)(3, n.stop)"),
        ("x in range(a, 10)", "__pyct_in__(x, __pyct_call__(range)(a, 10))"),
        ("x in range(1, 10)", "__pyct_in__(x, range(1, 10))"),
        ('"abc".find(s)', "__pyct_method__('abc'.find, s)"),
        ("'abc'.startswith(s, 1)", "__pyct_method__('abc'.startswith, s, 1)"),
        ("','.split(sep=s)", "__pyct_method__(','.split, sep=s)"),
        ("','.join(parts)", "__pyct_join__(','.join, parts)"),
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
        "map(range, stops)",
        "rng(n)",
        "range(*bounds)",
        "range()",
        # a range of int literals alone, which no argument can make tracked
        "range(3)",
        "range(-5, 5, 2)",
        "builtins.range(0, 10)",
        "text.find(s)",
        "items.index(x)",
        "b'abc'.find(s)",
        "f'{a}'.find(s)",
        "'abc'.__contains__(s)",
        # `type` with other than one argument alone: three build a class, and the rest refuse
        "type('C', (), {})",
        "type(x, 1)",
        "type(x, k=1)",
        "type(object=x)",
        "type(*args)",
        "map(type, values)",
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


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import math\nmath.sqrt(x)", "import math\n__pyct_call__(math.sqrt)(x)"),
        ("import math as m\nm.gcd(n, 6)", "import math as m\n__pyct_call__(m.gcd)(n, 6)"),
        (
            "import os, math\nmath.isclose(a=x, b=0.1)",
            "import os, math\n__pyct_call__(math.isclose)(a=x, b=0.1)",
        ),
        ("from math import sqrt\nsqrt(x)", "from math import sqrt\n__pyct_call__(sqrt)(x)"),
        (
            "from math import sqrt as root\nroot(x)",
            "from math import sqrt as root\n__pyct_call__(root)(x)",
        ),
        ("from math import *\nexp(x)", "from math import *\n__pyct_call__(exp)(x)"),
        # two functions of math under one name: the callee read when the call runs picks
        (
            "from math import sqrt, exp as sqrt\nsqrt(x)",
            "from math import sqrt, exp as sqrt\n__pyct_call__(sqrt)(x)",
        ),
        # bound in a function's scope, and read in another: every binding is the import
        (
            "def f():\n    import math\ndef g():\n    return math.log(x)",
            "\ndef f():\n    import math\n\ndef g():\n    return __pyct_call__(math.log)(x)",
        ),
    ],
)
def test_a_call_of_a_math_function_by_the_name_the_module_imports_it_under_is_substituted(
    source: str, expected: str
) -> None:
    assert substituted(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        # a name that ends like a math function but names no import of it
        "logger.log(x)",
        "obj.sqrt(x)",
        "pow(a, 2)",
        "def dist(a, b):\n    return a\ndist(1, 2)",
        "sqrt(x)",
        "math.sqrt(x)",
        # a module imported under math's name, and math imported under another's
        "import numpy as math\nmath.sqrt(x)",
        "import math as np\nimport numpy as np\nnp.exp(x)",
        # a name the module binds another way too
        "from math import sqrt\ndef sqrt(v):\n    return v\nsqrt(x)",
        "from math import sqrt\nsqrt = abs\nsqrt(x)",
        "import math\ndef f(math):\n    return math.sqrt(x)",
        "import math\nfor math in mods:\n    math.sqrt(x)",
        "from math import sqrt\nimport math as sqrt\nsqrt(x)",
        "import math\nmath = 2.0\nmath.sqrt(x)",
        # another module's star import may bind any name
        "from math import sqrt\nfrom cmath import *\nsqrt(x)",
        "import math\nfrom os import *\nmath.sqrt(x)",
        # a relative star import reads the package's own module, whatever its name
        "from math import sqrt\nfrom .math import *\nsqrt(x)",
        "import math\nfrom ..math import *\nmath.sqrt(x)",
        # an attribute of an attribute, and a name math does not route
        "import math\nself.math.sqrt(x)",
        "import math\nmath.floor(x)",
        "from math import ceil\nceil(x)",
        "import math\nmath.pi(x)",
        # a relative import, and a call with nothing written out
        "from .math import sqrt\nsqrt(x)",
        "import math\nmath.sqrt(*args)",
    ],
)
def test_any_other_call_of_a_math_name_is_left_as_written(source: str) -> None:
    assert substituted(source) == ast.unparse(ast.parse(source))
