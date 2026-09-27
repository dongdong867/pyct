"""Which `return` statements the transform hands to pyct: those of a `__bool__` method."""

import ast

import pytest

from pyct.intercept.substitute import substitute
from tests.acceptance.harness import REPO_ROOT
from tests.unit.intercept.test_lines_up import compared, layout

FIXTURE = REPO_ROOT / "targets" / "bools" / "bool_methods.py"

# a bool method's `return` with its value spread over lines, one per rule for where the value's
# first instruction is
SPREAD_OUT = [
    "return (\n    self.v\n    != 0)",
    "return (self.v\n    != 0)",
    "return bool(\n    self.v)",
    "return (\n    bool)(self.v)",
    "return (a and\n    b)",
    "return (a\n    or b)",
    "return (a if\n    t else\n    b)",
    "return not (\n    a)",
    "return (\n    a).b(c)",
    "if a:\n    return b\nreturn (c\n    > 0)",
    "for x in y:\n    if x:\n        return (x\n        > 0)\nreturn False",
    "try:\n    return (a\n        == b)\nexcept E:\n    return False",
]


def returns(source: str) -> list[str]:
    """Each `return` of the substituted module, written back as Python, in the order written."""
    tree = substitute(ast.parse(source))
    found = [node for node in ast.walk(tree) if isinstance(node, ast.Return)]
    return [ast.unparse(node) for node in sorted(found, key=lambda node: node.lineno)]


def method(body: str, name: str = "__bool__") -> str:
    """A class whose method of that name has the given body, indented under it."""
    indented = "\n".join(f"        {line}" for line in body.splitlines())
    return f"class C:\n    def {name}(self):\n{indented}\n"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("return self.v != 0", ["return __pyct_truth__(self.v != 0)"]),
        ("return bool(self.v)", ["return __pyct_truth__(__pyct_call__(bool)(self.v))"]),
        ("return self.v", ["return __pyct_truth__(self.v)"]),
        ("return not self.v", ["return __pyct_truth__(not self.v)"]),
        ("return self.v in s", ["return __pyct_truth__(__pyct_in__(self.v, s))"]),
        (
            "if self.a:\n    return self.a > 0\nreturn self.b < 0",
            ["return __pyct_truth__(self.a > 0)", "return __pyct_truth__(self.b < 0)"],
        ),
        # the value `and`, `or` or a ternary picks is what the method returns, each handed over
        ("return a and b", ["return __pyct_truth__(a) and __pyct_truth__(b)"]),
        (
            "return a or (b and c)",
            ["return __pyct_truth__(a) or (__pyct_truth__(b) and __pyct_truth__(c))"],
        ),
        ("return a if t else b", ["return __pyct_truth__(a) if t else __pyct_truth__(b)"]),
        # a value CPython folds to a constant is never tracked, so it stays as written
        ("return True", ["return True"]),
        ("return 1", ["return 1"]),
        ("return a and False", ["return __pyct_truth__(a) and False"]),
        ("return", ["return"]),
    ],
)
def test_each_return_of_a_bool_method_hands_its_value_over(body: str, expected: list[str]) -> None:
    assert returns(method(body)) == expected


@pytest.mark.parametrize(
    "source",
    [
        # a function nested in the method, and a lambda there, keep their own `return`
        method("def check():\n    return self.v != 0"),
        "def __bool__(v):\n    return v != 0\n",
        method("return self.v != 0", name="__len__"),
        method("return self.v != 0", name="__nonzero__"),
        "class C:\n    async def __bool__(self):\n        return self.v != 0\n",
        "class C:\n    class D:\n        pass\n    def f(self):\n        return self.v != 0\n",
        "def f():\n    class C:\n        def g(self):\n            def __bool__():\n"
        "                return x != 0\n            return __bool__\n",
    ],
)
def test_any_other_return_stays_as_written(source: str) -> None:
    assert "__pyct_truth__" not in ast.unparse(substitute(ast.parse(source)))


def test_a_nested_function_s_return_stays_and_the_method_s_own_is_handed_over() -> None:
    body = "def check():\n    return self.v != 0\nhold = lambda: self.v != 0\nreturn check()"

    assert returns(method(body)) == ["return self.v != 0", "return __pyct_truth__(check())"]


def test_a_class_nested_anywhere_has_its_bool_method_s_return_handed_over() -> None:
    source = "def f():\n    class C:\n        def __bool__(self):\n            return x != 0\n"

    assert returns(source) == ["return __pyct_truth__(x != 0)"]


def test_the_call_takes_the_value_s_position_and_its_name_the_value_s_first_instruction() -> None:
    tree = substitute(ast.parse(method("return (\n    self.v\n    != 0)")))
    (returned,) = [node for node in ast.walk(tree) if isinstance(node, ast.Return)]
    call = returned.value

    assert isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    assert (call.lineno, call.col_offset, call.end_lineno) == (4, 12, 5)
    assert (call.func.lineno, call.func.col_offset) == (4, 12)
    # the value is the compare as written, moved into the call
    assert ast.unparse(call.args[0]) == "self.v != 0"


def test_the_module_binds_the_name_and_the_class_declares_it_global() -> None:
    tree = substitute(ast.parse(method("return self.v != 0")))
    binding, owner = tree.body

    assert isinstance(binding, ast.ImportFrom)
    assert [(alias.name, alias.asname) for alias in binding.names] == [("truth", "__pyct_truth__")]
    assert isinstance(owner, ast.ClassDef) and isinstance(owner.body[0], ast.Global)
    assert owner.body[0].names == ["__pyct_truth__"]


@pytest.mark.parametrize("shape", SPREAD_OUT)
def test_a_bool_method_s_return_spread_over_lines_lines_up(shape: str) -> None:
    source = method(shape)
    written = compile(source, "<m>", "exec")
    tree = substitute(ast.parse(source))
    substituted = compile(tree, "<m>", "exec")

    assert "__pyct_truth__" in ast.unparse(tree), shape
    assert layout(written) == layout(substituted)


# return-a-real-bool-from-a-bool-method-lines-up-with-the-method-as-written
def test_the_bool_method_fixture_lines_up_and_is_substituted() -> None:
    assert compared(FIXTURE) == (True, True)
    # the method whose `return` spreads its value over three lines hands it over
    tree = substitute(ast.parse(FIXTURE.read_text()))
    (spread,) = [node for node in tree.body if getattr(node, "name", None) == "Spread"]
    (returned,) = [node for node in ast.walk(spread) if isinstance(node, ast.Return)]
    assert ast.unparse(returned) == "return __pyct_truth__(self.v != 0)"
