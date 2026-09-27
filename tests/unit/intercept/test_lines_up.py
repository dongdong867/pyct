"""Every substituted module lines up with the module as written.

intercept-builtin-functions-lines-up-each-substituted-module-with-the-original. Each file of
the corpus is compiled as written and as pyct substitutes it, and each pair of code objects
must have the same lines, the same line starts in the same order, jump targets marked, and
every conditional jump at the same line and column. A line start is where ``sys.monitoring``
fires a line event, so these are the lines a run covers and the order it covers them in.

The corpus is v2's own targets, four packages of the standard library, and a sample of real
libraries: two whole, and the core of a large one with its tests, whose asserts spread one
compare over several lines.
"""

import ast
import dis
import importlib.util
import sysconfig
import types
import warnings
from collections.abc import Iterator
from pathlib import Path

import pytest

from pyct.intercept.compiled import substituted_code
from pyct.intercept.substitute import substitute
from tests.acceptance.harness import REPO_ROOT

STDLIB = Path(sysconfig.get_paths()["stdlib"])

# each group of the corpus: where its files are, and the library that must be installed for it
CORPUS: dict[str, tuple[str | None, str]] = {
    "targets": (None, str(REPO_ROOT / "targets")),
    "json": (None, str(STDLIB / "json")),
    "email": (None, str(STDLIB / "email")),
    "argparse": (None, str(STDLIB / "argparse.py")),
    "logging": (None, str(STDLIB / "logging")),
    "werkzeug": ("werkzeug", ""),
    "validators": ("validators", ""),
    "sympy.core": ("sympy", "core"),
}

type Layout = tuple[str, frozenset[int], list[tuple[int, bool]], list[tuple[str, object]]]


def files_of(group: str) -> list[Path]:
    """The corpus group's Python files, or a skip when its library is not installed."""
    library, where = CORPUS[group]
    if library is None:
        root = Path(where)
    else:
        spec = importlib.util.find_spec(library)
        if spec is None or spec.origin is None:
            pytest.skip(f"{library} is not installed")
        root = Path(spec.origin).parent / where
    return [root] if root.is_file() else sorted(root.rglob("*.py"))


def code_objects(code: types.CodeType) -> Iterator[types.CodeType]:
    yield code
    for constant in code.co_consts:
        if isinstance(constant, types.CodeType):
            yield from code_objects(constant)


def line_starts(code: types.CodeType) -> list[tuple[int, bool]]:
    """Each instruction after RESUME that starts a line, or that a jump lands on, with its line."""
    starts: list[tuple[int, bool]] = []
    previous: int | None = None
    resumed = False
    for step in dis.get_instructions(code):
        line = step.positions.lineno if step.positions else None
        if resumed and line is not None and (line != previous or step.is_jump_target):
            starts.append((line, step.is_jump_target))
        resumed = resumed or step.opname == "RESUME"
        previous = line
    return starts


def layout(code: types.CodeType) -> list[Layout]:
    """What a line tracer and a branch read off each code object: name, lines, starts, jumps."""
    return [
        (
            each.co_name,
            frozenset(line for _, _, line in each.co_lines() if line),
            line_starts(each),
            [
                (step.opname, step.positions)
                for step in dis.get_instructions(each)
                if step.opname.startswith("POP_JUMP_IF")
            ],
        )
        for each in code_objects(code)
    ]


def compared(path: Path) -> tuple[bool, bool] | None:
    """Whether the file lines up, and whether pyct substituted anything in it; None if it does
    not compile as written."""
    source = path.read_bytes()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            written = compile(source, str(path), "exec", dont_inherit=True)
        except SyntaxError:
            return None
        substituted = substituted_code(source, str(path))
    changed = ast.dump(ast.parse(source)) != ast.dump(substitute(ast.parse(source)))
    return layout(written) == layout(substituted), changed


@pytest.mark.parametrize("group", CORPUS)
def test_each_substituted_module_lines_up_with_the_original(group: str) -> None:
    results = {path: compared(path) for path in files_of(group)}

    compiled = {path: result for path, result in results.items() if result is not None}
    assert [str(path) for path, (same, _) in compiled.items() if not same] == []
    # the group holds substitutions, so it checks something
    assert any(changed for _, changed in compiled.values()), group


# compares whose left side spans lines, one per rule for where its first instruction is
SPREAD_OUT = [
    "(1 +\n 2) in b",
    "(-\n 1) in b",
    "(a +\n b) in c",
    "(a,\n b) in c",
    "(1,\n 2) in c",
    "[a,\n b] in c",
    "[\n *a, b] in c",
    "[1, 2,\n 3] in c",
    "(a or\n b) in c",
    "(a if\n t else b) in c",
    "f(\n x)[0] in c",
    "(\n x).y(*z) in c",
    "(\n x).y(z) in c",
    "[x for x in\n y] in c",
    "{x: 1 for x in\n y} in c",
    "(x for x in\n y) in c",
    "f'{\n a}' in c",
    "{\n a: 1} in c",
    "{\n a: 1, 'b':\n 2} in c",
    "{'a':\n f(), 'b': 2} in c",
    "{\n **a, 1: 2} in c",
    "(yield\n a) in c",
    "(a :=\n b) is True",
    "not (\n a).b in c",
    "x in [\n __debug__, 1]",
    "x in [\n 'ab' * 3000, 1]",
    "(\n handler\n)(request) in allowed",
    "(\n f)() is True",
    "{" + ", ".join(f"k{n}: {n}" for n in range(15)) + ",\n k: 1} in d",
    "{" + ", ".join(f"k{n}: {n}" for n in range(16)) + ",\n k: 1} in d",
    "{'a':\n f(), 'b': 2, **c} in d",
]


@pytest.mark.parametrize("shape", SPREAD_OUT)
def test_a_compare_whose_left_side_spans_lines_lines_up(shape: str) -> None:
    source = "def f():\n    " + shape.replace("\n", "\n    ") + "\n"
    written = compile(source, "<f>", "exec")
    substituted = compile(substitute(ast.parse(source)), "<f>", "exec")

    assert layout(written) == layout(substituted)


# modules whose first statement's first instruction is not at the statement's own start, each
# with a substitution further down, so the module imports the names it calls
FIRST_STATEMENTS = [
    "@decorate\ndef f():\n    pass",
    "@decorate\nclass C:\n    pass",
    "__all__ = [\n    'a',\n    'b',\n]",
    "TABLE = {\n    'a': 1,\n}",
    "if (\n    a):\n    pass",
    "with (\n    cm()):\n    pass",
    "global x\nx = 1",
    '"""doc"""\nfrom __future__ import annotations\n@decorate\ndef f():\n    pass',
]


@pytest.mark.parametrize("first", FIRST_STATEMENTS)
def test_a_module_whose_first_statement_starts_late_lines_up(first: str) -> None:
    source = first + "\ny = a in b\n"
    written = compile(source, "<m>", "exec")
    substituted = compile(substitute(ast.parse(source)), "<m>", "exec")

    assert layout(written) == layout(substituted)


def test_a_compare_whose_left_side_runs_on_a_later_line_lines_up() -> None:
    # `assert (` then the operand on the next line: the operand's first instruction is on the
    # later line, where the call's name goes too, so the compare's own line does not start first
    source = "def f(x):\n    assert (\n        x + 1).bit_length() is True\n"
    written = compile(source, "<f>", "exec")
    substituted = compile(substitute(ast.parse(source)), "<f>", "exec")

    assert layout(written) == layout(substituted)
    (function,) = [each for each in substituted.co_consts if isinstance(each, types.CodeType)]
    assert line_starts(function)[:2] == [(3, False), (2, False)]


def test_each_operand_node_appears_once_in_the_substituted_tree() -> None:
    source = (REPO_ROOT / "targets" / "intercept" / "positions.py").read_text()
    source += "\ny = not (x in [1, 2]) and (True is not z) and (a in {'k': b})\n"
    tree = substitute(ast.parse(source))

    nodes = [id(node) for node in ast.walk(tree) if isinstance(node, ast.expr)]
    assert len(nodes) == len(set(nodes))
