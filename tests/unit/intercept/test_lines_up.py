"""Every substituted module lines up with the module as written.

intercept-builtin-functions-lines-up-each-substituted-module-with-the-original. Each file of
the corpus is compiled as written and as pyct substitutes it, and each pair of code objects
must have the same lines, the same steps from one line to the next, and the same conditional
jumps, each copy counted, at the same position with the same target line and the same kind. A
line start is where ``sys.monitoring`` fires a line event, so these are the lines a run covers
and the order it covers them in. The one change of kind allowed is a fused None test, which a
substituted `is None` link makes a truth test on the same outcome (see `jump_kind`). No other
instruction is compared: substitution changes them.

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
    # modules where CPython copies a function's short last block into each branch
    "random": (None, str(STDLIB / "random.py")),
    "statistics": (None, str(STDLIB / "statistics.py")),
    "_pydecimal": (None, str(STDLIB / "_pydecimal.py")),
    "glob": (None, str(STDLIB / "glob.py")),
    "werkzeug": ("werkzeug", ""),
    "validators": ("validators", ""),
    "sympy.core": ("sympy", "core"),
}

type Layout = tuple[
    str, frozenset[int], frozenset[tuple[int | None, int]], list[tuple[object, int | None, str]]
]


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


# how control leaves an instruction without falling through to the next one
_NO_FALLTHROUGH = frozenset(
    {
        "RETURN_VALUE",
        "RETURN_CONST",
        "RAISE_VARARGS",
        "RERAISE",
        "JUMP_FORWARD",
        "JUMP_BACKWARD",
        "JUMP_BACKWARD_NO_INTERRUPT",
    }
)
_JUMPS = frozenset(dis.hasjrel) | frozenset(dis.hasjabs)


def _successors(steps: list[dis.Instruction]) -> list[list[int]]:
    """The indexes control can go to from each instruction: the next one, and a jump's target."""
    at = {step.offset: index for index, step in enumerate(steps)}
    found: list[list[int]] = []
    for index, step in enumerate(steps):
        after = [] if step.opname in _NO_FALLTHROUGH else [index + 1]
        if step.opcode in _JUMPS and isinstance(step.argval, int) and step.argval in at:
            after.append(at[step.argval])
        found.append([each for each in after if each < len(steps)])
    return found


def _line(step: dis.Instruction) -> int | None:
    """An instruction's line, or None for RESUME and an instruction with no line of its own."""
    if step.opname == "RESUME" or step.positions is None:
        return None
    return step.positions.lineno


def line_order(code: types.CodeType) -> frozenset[tuple[int | None, int]]:
    """Which line can run right after which: each step from one line to another along the code.

    A line start is where ``sys.monitoring`` fires a line event, so these
    steps are the orders a run covers lines in, on every path. CPython copies
    a short block that ends a function, such as its last ``return``, into
    each branch that reaches it, and a longer one it jumps to instead; both
    take the same steps, so two codes that differ only there line up. The
    first line is a step from None, from RESUME, and an instruction with no
    line of its own passes control on without a step.
    """
    steps = [step for step in dis.get_instructions(code) if step.opname != "CACHE"]
    successors = _successors(steps)
    order: set[tuple[int | None, int]] = set()
    for index, step in enumerate(steps):
        start = _line(step)
        if start is None and step.opname != "RESUME":
            continue
        pending, seen = list(successors[index]), set()
        while pending:
            after = pending.pop()
            if after not in seen:
                seen.add(after)
                reached = _line(steps[after])
                if reached is None:
                    pending.extend(successors[after])
                elif reached != start:
                    order.add((start, reached))
    return frozenset(order)


# the jumps a substituted `is None` link turns into, and what may sit between its test and jump
_TRUTH_TESTS = frozenset({"POP_JUMP_IF_TRUE", "POP_JUMP_IF_FALSE"})
_BETWEEN = frozenset({"SWAP", "COPY", "NOP", "CACHE", "EXTENDED_ARG"})
# the steps that search `__pyct_identity__(None)`, as a substituted `is None` link compiles
_NONE_LINK = ("__pyct_identity__", None, "CALL", "CONTAINS_OP")


def jump_kind(opname: str, none_link: int | None) -> str:
    """A conditional jump's kind, a truth test on a substituted `is None` link read as the None
    test it stands for.

    ``none_link`` is the argument of the `CONTAINS_OP` right before the jump
    when it searches `__pyct_identity__(None)`, and None for any other jump.
    `x in __pyct_identity__(None)` is true exactly when `x` is None, and
    `not in` exactly when it is not. So `POP_JUMP_IF_TRUE` after `in`, or
    `POP_JUMP_IF_FALSE` after `not in`, jumps when `x` is None, as
    `POP_JUMP_IF_NONE` does, and the other two as `POP_JUMP_IF_NOT_NONE`.
    Every other jump keeps its own kind, so a flipped outcome differs.
    """
    if opname not in _TRUTH_TESTS or none_link is None:
        return opname
    jumps_on_none = (none_link == 0) == (opname == "POP_JUMP_IF_TRUE")
    return "POP_JUMP_IF_NONE" if jumps_on_none else "POP_JUMP_IF_NOT_NONE"


def _none_link(steps: list[dis.Instruction], jump: int) -> int | None:
    """The `CONTAINS_OP` argument of a substituted `is None` link the jump tests, or None."""
    if jump < 4:
        return None
    name, constant, call, contains = steps[jump - 4 : jump]
    shape = (name.argval, constant.argval, call.opname, contains.opname)
    loaded = name.opname.startswith("LOAD_") and constant.opname == "LOAD_CONST"
    return contains.arg if loaded and shape == _NONE_LINK else None


def conditional_jumps(code: types.CodeType) -> list[tuple[object, int | None, str]]:
    """Each conditional jump's position, the line it jumps to and its kind, every copy kept.

    CPython writes a loop's test twice, at its top and its end, so two copies
    of one jump are two entries, and a code that drops one differs.
    """
    every = list(dis.get_instructions(code))
    lines = {step.offset: _line(step) for step in every}
    steps = [step for step in every if step.opname not in _BETWEEN]
    return sorted(
        (
            (step.positions, lines.get(step.argval), jump_kind(step.opname, _none_link(steps, at)))
            for at, step in enumerate(steps)
            if step.opname.startswith("POP_JUMP_IF")
        ),
        key=repr,
    )


def layout(code: types.CodeType) -> list[Layout]:
    """What a line tracer and a branch read off each code object: name, lines, steps, jumps."""
    return [
        (
            each.co_name,
            frozenset(line for _, _, line in each.co_lines() if line),
            line_order(each),
            conditional_jumps(each),
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
    written = compile(source, "<f>", "exec")
    tree = substitute(ast.parse(source))
    substituted = compile(tree, "<f>", "exec")

    assert ast.dump(tree) != ast.dump(ast.parse(source)), shape
    assert layout(written) == layout(substituted)


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
    written = compile(source, "<f>", "exec")
    substituted = compile(substitute(ast.parse(source)), "<f>", "exec")

    assert layout(written) == layout(substituted)


def test_a_flipped_outcome_or_a_dropped_copy_is_a_difference() -> None:
    # `in` then a jump if true, and `not in` then a jump if false, jump when the value is None
    assert jump_kind("POP_JUMP_IF_TRUE", 0) == "POP_JUMP_IF_NONE"
    assert jump_kind("POP_JUMP_IF_FALSE", 1) == "POP_JUMP_IF_NONE"
    assert jump_kind("POP_JUMP_IF_FALSE", 0) == "POP_JUMP_IF_NOT_NONE"
    # the other outcome, a truth test on anything else, and the other None test all differ
    assert jump_kind("POP_JUMP_IF_TRUE", 1) != "POP_JUMP_IF_NONE"
    assert jump_kind("POP_JUMP_IF_FALSE", None) == "POP_JUMP_IF_FALSE"
    assert jump_kind("POP_JUMP_IF_NOT_NONE", None) != jump_kind("POP_JUMP_IF_NONE", None)
    # a loop's test is written twice, and both copies count
    loop = compile("def f(x):\n    while x is not None:\n        x = g()\n", "<f>", "exec")
    (inner,) = [each for each in loop.co_consts if isinstance(each, types.CodeType)]
    jumps = conditional_jumps(inner)
    assert len(jumps) == 2 and jumps[0] == jumps[1]
