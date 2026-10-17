"""Which assignments the transform hands to pyct before they unpack: those whose one target is a
tuple or a list with at most one star, unless the value is a tuple or list display."""

import ast

import pytest

from pyct.intercept.substitute import substitute
from tests.unit.intercept.test_lines_up import layout

# an unpack with its value spread over lines, one per rule for where the value's first and
# last instructions are
SPREAD_OUT = [
    "a, b = (\n    s.split(','))",
    "a, b = (s\n    .split(','))",
    "a, b = s.split(\n    ',')",
    "a, b = f(\n    x)",
    "a, b = (\n    x)",
    "a, b = (\n    x\n    .w)",
    "a, b = (\n    x.y(z)\n    .w())",
    "a, b = (\n    x\n    .w(*z))",
    "a, b = (x if\n    t else y)",
    "a, b = (x or\n    y)",
    "a, *b = (\n    s.split(','))",
    "(a,\n b) = s.split(',')",
    "[a,\n *b] = s.split(',')",
    "for p in q:\n    a, b = (p\n        .split('='))",
    "a, b = d[\n    k]",
    "a, b = (yield\n    x)",
]


def assigned(source: str) -> list[str]:
    """Each assignment of the substituted module, written back as Python, in the order written."""
    tree = substitute(ast.parse(source))
    found = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)]
    return [ast.unparse(node) for node in sorted(found, key=lambda node: node.lineno)]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("a, b = s.split(',')", "a, b = __pyct_unpack__(s.split(','), 2)"),
        ("[a, b, c] = parts", "[a, b, c] = __pyct_unpack__(parts, 3)"),
        ("(a,) = parts", "a, = __pyct_unpack__(parts, 1)"),
        ("a, *rest = parts", "a, *rest = __pyct_unpack_starred__(parts, 1)"),
        ("*rest, a, b = parts", "*rest, a, b = __pyct_unpack_starred__(parts, 2)"),
        ("[*rest] = parts", "[*rest] = __pyct_unpack_starred__(parts, 0)"),
        # a target of any kind counts, and a nested one counts once, as one place
        ("x.a, y[0] = parts", "x.a, y[0] = __pyct_unpack__(parts, 2)"),
        ("(a, b), c = parts", "(a, b), c = __pyct_unpack__(parts, 2)"),
        ("a, b = f()", "a, b = __pyct_unpack__(f(), 2)"),
        ("a, b = 'xy'", "a, b = __pyct_unpack__('xy', 2)"),
        # the value is substituted inside the call as anywhere else
        ("a, b = x in y", "a, b = __pyct_unpack__(__pyct_in__(x, y), 2)"),
    ],
)
def test_an_unpack_hands_its_value_and_count_over(source: str, expected: str) -> None:
    assert assigned(source) == [expected]


@pytest.mark.parametrize(
    "source",
    [
        # a tuple or list display on the right stays as written
        "a, b = b, a",
        "a, b = [b, a]",
        "a, b = (*x, y)",
        # a chained assignment, a name target, and two stars are not an unpack of one count
        "a, b = c = parts",
        "a = parts",
        "a[0] = parts",
        # a loop, a comprehension, a with and an annotated or augmented assignment keep theirs
        "for a, b in pairs:\n    pass",
        "[a for a, b in pairs]",
        "with f() as (a, b):\n    pass",
        "x: int = 1",
        "x += 1",
    ],
)
def test_any_other_assignment_stays_as_written(source: str) -> None:
    tree = substitute(ast.parse(source))

    assert "__pyct_unpack" not in ast.unparse(tree)


def test_the_call_takes_the_value_s_position_and_its_name_the_value_s_first_instruction() -> None:
    tree = substitute(ast.parse("a, b = (\n    s.split(','))"))
    (assignment,) = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)]
    call = assignment.value

    assert isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    assert (call.lineno, call.col_offset) == (2, 4)
    assert (call.func.lineno, call.func.col_offset) == (2, 4)
    counted = call.args[1]
    assert isinstance(counted, ast.Constant) and counted.value == 2
    assert (counted.lineno, counted.col_offset) == (2, 4)


def test_a_value_ending_on_a_later_line_s_attribute_is_handed_over_at_that_attribute() -> None:
    tree = substitute(ast.parse("a, b = (\n    x\n    .w)"))
    (assignment,) = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)]
    call = assignment.value

    # where CPython puts the value's own last instruction, the load of `w`
    assert isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    assert (call.lineno, call.col_offset) == (3, 5)
    assert (call.func.lineno, call.func.col_offset) == (2, 4)


def test_the_module_binds_the_names_and_a_class_declares_them_global() -> None:
    tree = substitute(ast.parse("class C:\n    a, b = p\n    c, *d = p\n"))
    binding, owner = tree.body

    assert isinstance(binding, ast.ImportFrom)
    assert [(alias.name, alias.asname) for alias in binding.names] == [
        ("unpack", "__pyct_unpack__"),
        ("unpack_starred", "__pyct_unpack_starred__"),
    ]
    assert isinstance(owner, ast.ClassDef) and isinstance(owner.body[0], ast.Global)
    assert owner.body[0].names == ["__pyct_unpack__", "__pyct_unpack_starred__"]


@pytest.mark.parametrize("shape", SPREAD_OUT)
def test_an_unpack_spread_over_lines_lines_up(shape: str) -> None:
    source = f"def f():\n{''.join(f'    {line}\n' for line in shape.splitlines())}"
    written = compile(source, "<m>", "exec")
    tree = substitute(ast.parse(source))
    substituted = compile(tree, "<m>", "exec")

    assert "__pyct_unpack" in ast.unparse(tree), shape
    assert layout(written) == layout(substituted)
