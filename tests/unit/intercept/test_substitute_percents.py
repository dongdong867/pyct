"""Which `%` the transform hands to pyct: a format beside a tuple display, a str literal's
format, and a name's `%=` with a tuple display; any other `%` stays as written."""

import ast

import pytest

from pyct.intercept.compiled import substituted_code
from pyct.intercept.substitute import substitute
from tests.unit.intercept.lines_up import lined_up

# a `%` with its parts spread over lines, one per place the format or the operand may start
SPREAD_OUT = [
    "t = ('<%s>'\n    % (a,))",
    "t = '<%s>' % (\n    a,\n    b)",
    "t = (fmt\n    .strip() % (a, b))",
    "t = ('%d items'\n    % n)",
    "t = '%s' % (\n    x.y)",
    "t = f(\n    '%s' % s)",
    "t = '<%s>' % (a,)\nreturn t",
    "if a:\n    t = 1\nt = '%s-%s' % (a, b)",
    "t = 'Message: %r\\n' 'Arguments: %s\\n' % (\n    m,\n    a)",
    "t = x\nt %= (\n    a,\n    b)",
    "if '%s' % (s,) in y:\n    return 1",
]


def substituted(source: str) -> str:
    """The substituted module's last statement, written back as Python."""
    return ast.unparse(substitute(ast.parse(source)).body[-1])


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("t = '<%s>' % (a,)", "t = __pyct_fstring_mod__('<%s>', (a,))"),
        # CPython compiles a str literal's `%` with a tuple display as an f-string only where its
        # compiled code shows it does
        ("t = '%5s|%r' % (a, b)", "t = __pyct_fstring_mod__('%5s|%r', (a, b))"),
        ("t = '%d' % (n,)", "t = __pyct_mod__('%d', (n,))"),
        ("t = '%*s' % (w, a)", "t = __pyct_mod__('%*s', (w, a))"),
        ("t = '%s' % (*xs,)", "t = __pyct_mod__('%s', (*xs,))"),
        ("t = fmt % (a, b)", "t = __pyct_formatter__(fmt)((a, b))"),
        ("t = self.f() % (a, *b)", "t = __pyct_formatter__(self.f())((a, *b))"),
        ("t = '%d items' % n", "t = __pyct_mod__('%d items', n)"),
        ("t = 'a' 'b%s' % d", "t = __pyct_mod__('ab%s', d)"),
        ("t = ('<' + '%s>') % s", "t = __pyct_mod__('<' + '%s>', s)"),
        ("t = '%(k)s' % {'k': s}", "t = __pyct_mod__('%(k)s', {'k': s})"),
        ("x %= (a, b)", "x = __pyct_in_place_formatter__(x)((a, b))"),
        # an operand is substituted inside the call as anywhere else
        ("t = '%s' % (a in b,)", "t = __pyct_fstring_mod__('%s', (__pyct_in__(a, b),))"),
    ],
)
def test_a_format_hands_its_operands_over(source: str, expected: str) -> None:
    assert substituted(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        # a name's format with an operand that is not a tuple display, and an int's remainder
        "t = fmt % s",
        "t = n % 2",
        "t = 0.5 % n",
        "t = b'%s' % x",
        # a right side CPython folds to a constant holds nothing tracked
        "t = '%d' % 5",
        "t = fmt % (1, 'x')",
        "x %= (2,)",
        # a `%=` on anything but a name, or with any other right side
        "x.a %= (b,)",
        "x[0] %= (b,)",
        "x %= b",
        "x += (b,)",
    ],
)
def test_any_other_percent_stays_as_written(source: str) -> None:
    assert "mod__" not in substituted(source)
    assert "formatter__" not in substituted(source)


def test_the_call_takes_the_operation_s_position_and_its_name_the_format_s_first() -> None:
    tree = substitute(ast.parse("t = (fmt\n    .strip() % (a, b))"))
    (assignment,) = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)]
    call = assignment.value

    assert isinstance(call, ast.Call) and isinstance(call.func, ast.Call)
    assert (call.lineno, call.col_offset, call.end_lineno) == (1, 5, 2)
    asked = call.func
    assert isinstance(asked.func, ast.Name) and asked.func.id == "__pyct_formatter__"
    assert (asked.lineno, asked.col_offset) == (asked.func.lineno, asked.func.col_offset) == (1, 5)


def test_an_augmented_format_assigns_the_call_at_the_statement_s_position() -> None:
    tree = substitute(ast.parse("x %= (a,\n    b)"))
    assignment = tree.body[-1]

    assert isinstance(assignment, ast.Assign) and isinstance(assignment.value, ast.Call)
    (target,) = assignment.targets
    assert isinstance(target, ast.Name) and isinstance(target.ctx, ast.Store)
    call = assignment.value
    assert (call.lineno, call.col_offset, call.end_lineno) == (1, 0, 2)
    assert isinstance(call.func, ast.Call)
    read = call.func.args[0]
    assert isinstance(read, ast.Name) and isinstance(read.ctx, ast.Load)
    assert (read.lineno, read.col_offset) == (target.lineno, target.col_offset)


def test_the_module_binds_the_names_and_a_class_declares_them_global() -> None:
    tree = substitute(ast.parse("class C:\n    t = '%s' % s\n    t %= (u,)\n"))
    binding, owner = tree.body

    assert isinstance(binding, ast.ImportFrom)
    assert [(alias.name, alias.asname) for alias in binding.names] == [
        ("mod", "__pyct_mod__"),
        ("in_place_formatter", "__pyct_in_place_formatter__"),
    ]
    assert isinstance(owner, ast.ClassDef) and isinstance(owner.body[0], ast.Global)
    assert owner.body[0].names == ["__pyct_mod__", "__pyct_in_place_formatter__"]


@pytest.mark.parametrize("shape", SPREAD_OUT)
def test_a_format_spread_over_lines_lines_up(shape: str) -> None:
    source = "def f():\n    " + shape.replace("\n", "\n    ") + "\n"

    assert "__pyct_" in ast.unparse(substitute(ast.parse(source))), shape
    assert lined_up(source, "<f>")


def test_a_format_written_as_a_long_chain_of_literals_loads_and_formats_as_written() -> None:
    # 1,000 links: deeper than a copy or a walk of the format that recurses one level a link
    # can go, and as deep as the operator rule's own search for folded parts runs in about a
    # second, a search that grows with the square of the chain
    chain = " +\n".join(["'a'"] * 999 + ["'%s'"])
    source = f"x = 'q'\nt = ({chain}) % (x,)\n"
    written: dict[str, object] = {}
    substituted: dict[str, object] = {}

    exec(compile(source, "<chain>", "exec"), written)  # noqa: S102 - the module above
    exec(substituted_code(source.encode(), "<chain>"), substituted)  # noqa: S102

    assert substituted["t"] == written["t"]
    assert any(name.startswith("__pyct_") for name in substituted)
