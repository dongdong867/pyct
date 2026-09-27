"""Which compares the transform substitutes, what it leaves alone, and what each call is handed."""

import ast
import time

import pytest

from pyct.core import substitutes
from pyct.core.bools import ConcolicBool
from pyct.core.branch import SinkItem
from pyct.core.hashed import SEARCHED_MOST
from pyct.intercept.compiled import SubstitutionError, substituted_code
from pyct.intercept.substitute import BOUND, substitute

# how the import a module with a substitution starts with begins
BINDING = "from pyct.core.substitutes import "


def substituted(source: str) -> str:
    """The source as the transform leaves it, written back as Python, less its binding import."""
    lines = ast.unparse(substitute(ast.parse(source))).splitlines()
    return "\n".join(line for line in lines if not line.startswith(BINDING))


def statements(source: str) -> list[ast.stmt]:
    """The substituted module's statements after its binding import."""
    body = substitute(ast.parse(source)).body
    assert isinstance(body[0], ast.ImportFrom), body
    return body[1:]


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
        "None is not a",
        # `is` between two operands neither of which is known to hold a bool
        "a is b",
        "a.b is not f()",
        "not (a is b)",
        "a < b is c",
        "a is 1",
        "a is ...",
        "not (a is None)",
        # a chained compare with no `in` link and no `is` link pyct takes, and an operator no
        # plain number can hand over
        "a < b < c",
        "a < b is None",
        "None is a < b",
        "a == 1",
        "not (a == 'x')",
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


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # the chain stays, and its link searches a container of pyct's, which asks `in_`
        ("0 < x in s", "0 < x in __pyct_searched__(s)"),
        ("0 < x not in s", "0 < x not in __pyct_searched__(s)"),
        # the last link's container is handed over as CPython compiles it beside `in`
        ("0 < x in {1, 5}", "0 < x in __pyct_searched__(frozenset({1, 5}), (1, 5))"),
        ("0 < x in [a, b]", "0 < x in __pyct_searched__((a, b))"),
        # an earlier link's display is compiled as written, and a set still hands its constants
        ("x in [1, 2] < y", "x in __pyct_searched__([1, 2]) < y"),
        ("x in {2, 1} < y", "x in __pyct_searched__({2, 1}, (2, 1)) < y"),
        ("x in {'a': 1} < y", "x in __pyct_searched__({'a': 1}, ('a',)) < y"),
        # `is` against True or False on its right is an `in` on pyct's identity
        ("1 == flag is True", "1 == flag in __pyct_identity__(True)"),
        ("1 == flag is not False", "1 == flag not in __pyct_identity__(False)"),
        ("a is False < b in c", "a in __pyct_identity__(False) < b in __pyct_searched__(c)"),
        # with True or False on its left, the right operand is the one pyct reads, so it is
        # the one the call holds
        ("True is flag < 3", "True in __pyct_identity__(flag) < 3"),
        ("True is flag is other", "True in __pyct_identity__(flag) in __pyct_identity__(other)"),
        ("0 < False is not flag", "0 < False not in __pyct_identity__(flag)"),
        # a link of any other operator is left to Python, and after a searched link it meets
        # the operand the call holds: a compare runs on it, and an `is` reads it through pyct
        ("a is None < b in c", "a is None < b in __pyct_searched__(c)"),
        ("None is a < b", "None is a < b"),
        ("a in b < c", "a in __pyct_searched__(b) < c"),
        ("a in b is c", "a in __pyct_searched__(b) in __pyct_identity__(c)"),
        # a link pyct takes before an `is` against None hands that `is` on to pyct too
        ("a in b is not None", "a in __pyct_searched__(b) not in __pyct_identity__(None)"),
        ("0 < x in s is None", "0 < x in __pyct_searched__(s) in __pyct_identity__(None)"),
        ("a is b is None", "a is b is None"),
        ("a is b is None < c in d", "a is b is None < c in __pyct_searched__(d)"),
        (
            "True is flag is not None",
            "True in __pyct_identity__(flag) not in __pyct_identity__(None)",
        ),
        (
            "flag is True is not None",
            "flag in __pyct_identity__(True) not in __pyct_identity__(None)",
        ),
    ],
)
def test_an_in_or_is_link_of_a_chain_searches_through_pyct(source: str, expected: str) -> None:
    assert substituted(source) == expected


# a lone `is` between two operands, one a name that holds a bool wherever the code binds it
BOOL_NAMES: dict[str, str] = {
    "a parameter annotated bool": "def f(flag: bool, other):\n    return flag is other",
    "an annotation kept as text": "def f(flag: 'bool', other):\n    return other is not flag",
    "a compare's answer": "def f(x, other):\n    done = x > 0\n    return done is other",
    "a negation": "def f(x, other):\n    done = not x\n    return other is done",
    "a bool() call": "def f(x, other):\n    done = bool(x)\n    return done is other",
    "a literal": "def f(other):\n    done = False\n    return done is other",
    "a walrus": "def f(x, other):\n    (done := x < 1)\n    return done is other",
    "a module-level name": "READY = 1 > 0\n\ndef f(other):\n    return other is READY",
    "a chain": "def f(flag: bool, other):\n    return 1 == flag is other",
    "a chain after an in": "def f(x, flag: bool):\n    return x in s is flag",
}
# the same shapes where a binding of the name is not a bool, or the name is not bound there
NOT_BOOL_NAMES: dict[str, str] = {
    "a parameter annotated int": "def f(flag: int, other):\n    return flag is other",
    "a parameter bound again": (
        "def f(flag: bool, other):\n    flag = g()\n    return flag is other"
    ),
    "a name bound twice": (
        "def f(x, other):\n    done = x > 0\n    done += 1\n    return done is other"
    ),
    "a loop target": (
        "def f(xs, other):\n    for done in xs:\n        pass\n    return done is other"
    ),
    "a tuple target": "def f(other):\n    done, rest = True, 1\n    return done is other",
    "a module name set elsewhere": (
        "READY = 1 > 0\n\ndef g():\n    global READY\n    READY = 3\n\n"
        "def f(other):\n    return other is READY"
    ),
    "a parameter named bool": "def f(bool, flag: bool, other):\n    return flag is other",
    "a star import": "from m import *\n\ndef f(flag: bool, other):\n    return flag is other",
    "an assignment under nonlocal": (
        "def f(o):\n    done = o > 1\n    def g():\n        nonlocal done\n        done = o\n"
        "    return done is o"
    ),
    "a type alias": "done = True\ntype done = int\n\ndef f(o):\n    return done is o",
    "a type parameter": "done = True\n\ndef f[done](o):\n    return done is o",
    "a class body's global": (
        "done = True\nclass A:\n    global done\n    done = 3\n\ndef f(o):\n    return done is o"
    ),
    "an unbound name": "def f(other):\n    return other is done",
}


@pytest.mark.parametrize("source", BOOL_NAMES.values(), ids=list(BOOL_NAMES))
def test_an_is_on_a_name_that_holds_a_bool_is_pyct_s(source: str) -> None:
    assert "__pyct_is" in substituted(source) or "__pyct_identity__" in substituted(source)


@pytest.mark.parametrize("source", NOT_BOOL_NAMES.values(), ids=list(NOT_BOOL_NAMES))
def test_an_is_on_any_other_name_is_python_s_own(source: str) -> None:
    assert substituted(source) == ast.unparse(ast.parse(source))


# chains whose `is` links pyct takes before an `is` against None, and plain Python's answer for
# a bool `flag` and `other` both True
BEFORE_NONE: list[str] = [
    "True is flag is not None",
    "flag is True is not None",
    "flag is other is not None",
]


@pytest.mark.parametrize("chain", BEFORE_NONE)
def test_a_bool_link_before_an_is_against_none_answers_as_plain_python(chain: str) -> None:
    source = f"def f(flag: bool, other: bool):\n    return {chain}\n"
    namespace: dict[str, object] = {}
    exec(compile(substitute(ast.parse(source)), "<f>", "exec"), namespace)
    sink: list[SinkItem] = []
    flag = ConcolicBool.made(True, expression="flag", sink=sink)
    other = ConcolicBool.made(True, expression="other", sink=sink)

    plain: dict[str, object] = {}
    exec(compile(source, "<f>", "exec"), plain)
    assert namespace["f"](flag, other) is plain["f"](True, True) is True  # pyrefly: ignore


def test_a_chain_link_s_call_takes_its_operand_s_position() -> None:
    (statement,) = statements("y = (0 < x in\n     s)")
    chain = statement.value  # pyrefly: ignore[missing-attribute]
    call = chain.comparators[1]

    assert (chain.lineno, chain.col_offset) == (1, 5)
    assert (call.lineno, call.col_offset, call.end_lineno) == (2, 5, 2)
    assert (call.func.lineno, call.func.col_offset) == (2, 5)


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
    elements = ", ".join(str(n) for n in range(SEARCHED_MOST + 1))
    (call,) = statements(f"x in {{{elements}}}")

    assert isinstance(call, ast.Expr) and isinstance(call.value, ast.Call)
    assert len(call.value.args) == 2


def test_an_element_that_cannot_stand_alone_is_no_constant() -> None:
    source = "async def f():\n    return x in [await g(), 1]"
    assert "__pyct_in__(x, (await g(), 1))" in substituted(source)


def test_a_deeply_nested_expression_needs_no_deep_stack() -> None:
    # a chain of 5,000 `+` over as many lines, which the walk and the search for the first
    # instruction each go down one step at a time
    chain = " +\n".join(["a"] * 5000)
    call = statements(f"({chain}) in b")[0].value  # pyrefly: ignore[missing-attribute]

    assert isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    assert (call.func.id, call.func.lineno) == ("__pyct_in__", 1)


def test_a_long_chain_over_many_lines_is_substituted_in_one_pass_over_it() -> None:
    # a chain of 5,000 `+` on a name and constants: which parts CPython folds is worked out
    # once, so the search for the first instruction does not walk the chain at every step
    chain = "x" + "".join(" +\n1" for _ in range(5000))
    started = time.perf_counter()
    statements(f"({chain}) in b")

    assert time.perf_counter() - started < 2.0


def test_each_call_takes_the_compare_s_position_and_its_name_the_first_operand_s_line() -> None:
    test = statements("if (\n    a).b in c:\n    pass")[0].test  # pyrefly: ignore[missing-attribute]

    assert (test.lineno, test.col_offset, test.end_lineno) == (1, 3, 2)
    assert (test.func.lineno, test.func.end_lineno) == (2, 2)


def test_the_bound_names_are_dunders_that_name_the_core_functions() -> None:
    assert all(name.startswith("__") and name.endswith("__") for name in BOUND)
    assert BOUND == {
        "__pyct_is__": "is_",
        "__pyct_is_not__": "is_not",
        "__pyct_in__": "in_",
        "__pyct_not_in__": "not_in",
        "__pyct_searched__": "Searched",
        "__pyct_identity__": "Identity",
        "__pyct_handed__": "handed",
        "__pyct_call__": "call",
        "__pyct_method__": "method",
        "__pyct_truth__": "truth",
    }
    assert all(hasattr(substitutes, function) for function in BOUND.values())


def test_a_repeated_constant_is_handed_over_once_as_the_display_holds_it() -> None:
    (statement,) = statements("x in {1, True, 1.0, 'a', 'a'}")
    call = statement.value  # pyrefly: ignore[missing-attribute]

    assert [arg.value for arg in call.args[1:]] == [frozenset({1, "a"}), (1, "a")]
    assert substituted("x in {'k': 1, 'k': 2}") == "__pyct_in__(x, {'k': 1, 'k': 2}, ('k',))"


def test_the_names_are_imported_before_the_first_statement_that_runs_on_its_line() -> None:
    source = '"""doc"""\nfrom __future__ import annotations\n\nimport os\ny = os in z\n'
    body = substitute(ast.parse(source)).body

    assert [type(each).__name__ for each in body] == [
        "Expr",
        "ImportFrom",
        "ImportFrom",
        "Import",
        "Assign",
    ]
    assert (body[2].lineno, body[2].end_lineno) == (4, 4)
    assert ast.unparse(body[2]) == f"{BINDING}in_ as __pyct_in__"


def test_a_module_imports_only_the_names_it_calls_in_the_order_bound() -> None:
    body = substitute(ast.parse("y = a not in b\nz = x is True\nw = int(v)\n")).body

    expected = "is_ as __pyct_is__, not_in as __pyct_not_in__, call as __pyct_call__"
    assert ast.unparse(body[0]) == BINDING + expected


def test_a_module_with_nothing_substituted_imports_nothing() -> None:
    assert ast.unparse(substitute(ast.parse("x = a == 1\n"))) == "x = a == 1"


def test_every_class_body_declares_the_names_global_after_its_docstring() -> None:
    source = 'class A:\n    """doc"""\n    x = 1 in y\n\n    class B:\n        z = 2\n'
    outer = statements(source)[0]

    assert isinstance(outer, ast.ClassDef)
    assert isinstance(outer.body[1], ast.Global) and outer.body[1].names == ["__pyct_in__"]
    inner = outer.body[3]
    assert isinstance(inner, ast.ClassDef) and isinstance(inner.body[0], ast.Global)


def test_the_bound_names_are_reserved_in_a_class_body() -> None:
    # a class body declares them global, so a class that binds one binds the module's name
    source = "class A:\n    __pyct_in__ = len\n    z = x is True\n"
    namespace: dict[str, object] = {"x": True}

    exec(compile(substitute(ast.parse(source)), "<a>", "exec"), namespace)

    assert namespace["__pyct_in__"] is len
    assert namespace["A"].z is True  # pyrefly: ignore[missing-attribute]
    # one annotated in a class body cannot be global, so the module does not load
    with pytest.raises(SubstitutionError, match="can't be global"):
        substituted_code(b"class A:\n    __pyct_in__: object = len\n    y = 1 in (1,)\n", "a.py")
