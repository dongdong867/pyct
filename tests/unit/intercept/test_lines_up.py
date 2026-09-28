"""Every substituted module lines up with the module as written.

intercept-builtin-functions-lines-up-each-substituted-module-with-the-original. Each file of
the corpus is compiled as written and as pyct substitutes it, and the two must line up as
`tests.unit.intercept.lines_up` reads them: the same lines, steps and conditional jumps.

The corpus is v2's own targets, modules of the standard library, and a sample of real
libraries: two whole, and the core of a large one with its tests, whose asserts spread one
compare over several lines.
"""

import ast
import dis
import importlib.util
import sysconfig
import types
import warnings
from pathlib import Path

import pytest

from pyct.intercept.compiled import substituted_code
from pyct.intercept.substitute import substitute
from tests.acceptance.harness import REPO_ROOT
from tests.unit.intercept.lines_up import (
    code_objects,
    conditional_jumps,
    jump_kind,
    layout,
    line_starts,
    lined_up,
    negations,
)

STDLIB = Path(sysconfig.get_paths()["stdlib"])

# each group of the corpus: where its files are, and the library that must be installed for it
CORPUS: dict[str, tuple[str | None, str]] = {
    "targets": (None, str(REPO_ROOT / "targets")),
    "json": (None, str(STDLIB / "json")),
    "email": (None, str(STDLIB / "email")),
    "argparse": (None, str(STDLIB / "argparse.py")),
    "logging": (None, str(STDLIB / "logging")),
    # modules where CPython copies a function's short last block into each branch
    "random": (None, str(STDLIB / "random.py")),
    "statistics": (None, str(STDLIB / "statistics.py")),
    "_pydecimal": (None, str(STDLIB / "_pydecimal.py")),
    "glob": (None, str(STDLIB / "glob.py")),
    "werkzeug": ("werkzeug", ""),
    "validators": ("validators", ""),
    "sympy.core": ("sympy", "core"),
}


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
    tree = substitute(ast.parse(source))
    changed = ast.dump(ast.parse(source)) != ast.dump(tree)
    return layout(written) == layout(substituted, negations(tree)), changed


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
    # a chained compare's `in` link and its `is` link against True or False
    "0 < (\n x) in c",
    "0 < x in {\n 1, 5}",
    "0 < x in [\n 1, 2]",
    "x in [\n 1, 2] < y",
    "x in {\n 1, 2} < y",
    "(\n a) < x not in {'k':\n 1}",
    "1 == (\n flag) is True",
    "flag is (\n False) == 1",
    "if 0 < x in c < (\n y):\n    pass",
    "if a is b is None:\n    pass",
    "if x in c is not (\n None):\n    pass",
    "if a is (\n b) < c:\n    pass",
]


# calls and operators spread over lines, one per rule for where their parts' instructions are
CALLS_AND_OPERATORS_SPREAD_OUT = [
    "int(\n x)",
    "(\n int)(x)",
    "builtins.int(\n x)",
    "'abc'.find(\n s)",
    "'abc'.find(s,\n 1)",
    "map(\n int, xs)",
    "range(\n n)",
    "builtins.range(\n a, b)",
    "for i in range(\n n):\n pass",
    "if x in range(\n 1, 9):\n pass",
    "while x not in range(a,\n b, -1):\n break",
    "'abc'.index(\n s)",
    "(0.5 +\n b)",
    "(0.5\n + b)",
    "(True\n * n)",
    "(0.5 + f(\n x))",
    "(0.5 + a\n .b)",
    "(-\n 0.5) - b",
    "(0.5 +\n b +\n c)",
    "(2.5 <\n b)",
    "if (2.5 <\n b):\n pass",
    "if int(\n x):\n pass",
    "if 'abc'.startswith(\n s):\n pass",
    "while (True\n != b):\n break",
    "assert (\n 0.5) == b",
    "x = 1.5 / (n if t else\n m)",
    "y = not (False\n == b)",
    "z = 0.5 + (x\n .bit_length())",
    # a short last block CPython copies into each branch, which the substituted one outgrows
    "if a:\n d = 1\nelse:\n d = 2\nreturn float(s)",
    "if a:\n d = 1\nelse:\n d = 2\nreturn 1.5 / d",
    "if a:\n d = 1\nelse:\n d = 2\nreturn 'x'.find(s)",
]


@pytest.mark.parametrize("shape", CALLS_AND_OPERATORS_SPREAD_OUT)
def test_a_call_or_operator_spread_over_lines_lines_up(shape: str) -> None:
    source = "def f():\n    " + shape.replace("\n", "\n    ") + "\n"
    tree = substitute(ast.parse(source))

    assert ast.dump(tree) != ast.dump(ast.parse(source)), shape
    assert lined_up(source, "<f>")


@pytest.mark.parametrize("shape", SPREAD_OUT)
def test_a_compare_whose_left_side_spans_lines_lines_up(shape: str) -> None:
    source = "def f():\n    " + shape.replace("\n", "\n    ") + "\n"

    assert lined_up(source, "<f>")


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

    assert lined_up(source, "<m>")


def test_a_compare_whose_left_side_runs_on_a_later_line_lines_up() -> None:
    # `assert (` then the operand on the next line: the operand's first instruction is on the
    # later line, where the call's name goes too, so the compare's own line does not start first
    source = "def f(x):\n    assert (\n        x + 1).bit_length() is True\n"
    substituted = compile(substitute(ast.parse(source)), "<f>", "exec")

    assert lined_up(source, "<f>")
    (function,) = [each for each in substituted.co_consts if isinstance(each, types.CodeType)]
    assert line_starts(function)[:2] == [(3, False), (2, False)]


def test_each_operand_node_appears_once_in_the_substituted_tree() -> None:
    source = (REPO_ROOT / "targets" / "intercept" / "positions.py").read_text()
    source += "\ny = not (x in [1, 2]) and (True is not z) and (a in {'k': b})\n"
    tree = substitute(ast.parse(source))

    nodes = [id(node) for node in ast.walk(tree) if isinstance(node, ast.expr)]
    assert len(nodes) == len(set(nodes))


def test_a_step_between_lines_that_changes_does_not_line_up() -> None:
    # the same lines, run in another order: the check must see the difference
    first = compile("def f(a, b):\n    x = (a,\n        b)\n", "<f>", "exec")
    swapped = ast.parse("def f(a, b):\n    x = (a,\n        b)\n")
    pair = swapped.body[0].body[0].value  # pyrefly: ignore[missing-attribute]
    pair.elts[0].lineno = pair.elts[0].end_lineno = 3
    pair.elts[1].lineno = pair.elts[1].end_lineno = 2
    second = compile(swapped, "<f>", "exec")

    assert layout(first) != layout(second)


def _jump_kinds(code: types.CodeType) -> set[str]:
    return {
        step.opname
        for each in code_objects(code)
        for step in dis.get_instructions(each)
        if step.opname.startswith("POP_JUMP_IF")
    }


def test_a_fused_none_test_that_becomes_a_truth_test_lines_up_and_nothing_wider() -> None:
    source = (
        "def f(flag: bool):\n    if True is flag is not None:\n        return 1\n    return 2\n"
    )
    written = compile(source, "<f>", "exec")
    substituted = compile(substitute(ast.parse(source)), "<f>", "exec")

    # the one difference: the `is not None` jump is a truth test on the same outcome
    assert _jump_kinds(written) == {"POP_JUMP_IF_FALSE", "POP_JUMP_IF_NONE"}
    assert _jump_kinds(substituted) == {"POP_JUMP_IF_FALSE"}
    assert layout(written) == layout(substituted)
    # a jump at another column, or to another line, is still a difference
    moved = compile(source.replace("if True", "if (True)"), "<f>", "exec")
    assert layout(moved) != layout(written)
    elsewhere = compile(source.replace("return 2", "pass\n    return 2"), "<f>", "exec")
    assert layout(elsewhere) != layout(written)


@pytest.mark.parametrize(
    "test", ["True is flag is not None", "True is flag is None", "False or flag is True is None"]
)
def test_a_substituted_none_test_keeps_its_outcome(test: str) -> None:
    source = f"def f(flag: bool):\n    if {test}:\n        return 1\n    return 2\n"

    assert lined_up(source, "<f>")


def test_a_flipped_outcome_or_a_dropped_copy_is_a_difference() -> None:
    # `in` then a jump if true, and `not in` then a jump if false, jump when the value is None
    assert jump_kind("POP_JUMP_IF_TRUE", 0) == "POP_JUMP_IF_NONE"
    assert jump_kind("POP_JUMP_IF_FALSE", 1) == "POP_JUMP_IF_NONE"
    assert jump_kind("POP_JUMP_IF_FALSE", 0) == "POP_JUMP_IF_NOT_NONE"
    # the other outcome, a truth test on anything else, and the other None test all differ
    assert jump_kind("POP_JUMP_IF_TRUE", 1) != "POP_JUMP_IF_NONE"
    assert jump_kind("POP_JUMP_IF_FALSE", None) == "POP_JUMP_IF_FALSE"
    assert jump_kind("POP_JUMP_IF_NOT_NONE", None) != jump_kind("POP_JUMP_IF_NONE", None)
    # a finally body is written twice, and both copies count
    source = "def f(x):\n try:\n  g()\n finally:\n  if x is not None:\n   h()\n"
    code = compile(source, "<f>", "exec")
    (inner,) = [each for each in code.co_consts if isinstance(each, types.CodeType)]
    jumps = conditional_jumps(inner)
    assert len(jumps) == 2 and jumps[0] == jumps[1]


# a `not` over a compare pyct substitutes, in each place a truth test reads it
NEGATED_TESTS = [
    "if not x in c:\n    pass",
    "if not x is True:\n    pass",
    "if not (x in c):\n    pass",
    "if not not x in c:\n    pass",
    "if x not in c:\n    pass",
    "if a and not x in c:\n    pass",
    "while not x is False:\n    break",
    "assert not x in c",
    "y = [v for v in w if not v in c]",
]


# a `not` over a compare pyct substitutes, inside a `__bool__` method's return
NEGATED_RETURNS = ["return (not x in c) and y", "return (not x is True) or y"]


@pytest.mark.parametrize("shape", NEGATED_RETURNS)
def test_a_negated_compare_in_a_bool_method_s_return_lines_up(shape: str) -> None:
    source = f"class A:\n    def __bool__(self):\n        {shape}\n"

    assert "__pyct_truth__" in ast.unparse(substitute(ast.parse(source)))
    assert lined_up(source, "<m>")


@pytest.mark.parametrize("shape", NEGATED_TESTS)
def test_a_negated_compare_pyct_substitutes_lines_up(shape: str) -> None:
    source = "def f():\n    " + shape.replace("\n", "\n    ") + "\n"

    assert lined_up(source, "<f>")


def test_a_negated_test_read_on_its_outcome_still_differs_when_the_outcome_flips() -> None:
    # after `not in`, or pyct's call for it, a truth test reads as the other one after `in`
    assert jump_kind("POP_JUMP_IF_FALSE", None, negated=True) == "POP_JUMP_IF_TRUE"
    assert jump_kind("POP_JUMP_IF_TRUE", None, negated=True) == "POP_JUMP_IF_FALSE"
    assert jump_kind("POP_JUMP_IF_NONE", None, negated=True) == "POP_JUMP_IF_NONE"
    # `x in c` where `not x in c` was, at the same column: the same jump on the other outcome
    negated = "def f():\n    if not x in c:\n        return 1\n"
    tree = substitute(ast.parse(negated))
    plain = compile(negated.replace("not x", "    x"), "<f>", "exec")
    assert layout(plain) != layout(compile(tree, "<f>", "exec"), negations(tree))
