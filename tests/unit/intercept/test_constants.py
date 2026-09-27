"""Which names a module binds to literals alone, which the rules read as they read a literal."""

import ast
import sys
import types

import pytest

from pyct.intercept import constants
from pyct.intercept.constants import literal_names
from tests.unit.intercept.test_substitute import substituted


def kinds(source: str) -> dict[str, frozenset[type]]:
    return literal_names(ast.parse(source)).kinds


def test_a_name_bound_to_literals_alone_holds_their_kinds() -> None:
    source = "RATE = 0.5\nFLAG: bool = True\ndef f():\n    RATE = 1.5\n    TEXT = 'x'\n"

    assert kinds(source) == {
        "RATE": frozenset({float}),
        "FLAG": frozenset({bool}),
        "TEXT": frozenset({str}),
    }


def test_a_name_bound_to_literals_of_two_kinds_holds_both() -> None:
    assert kinds("A = 0.5\nA = True\n") == {"A": frozenset({float, bool})}


@pytest.mark.parametrize(
    "binding",
    [
        "RATE = f()",
        "RATE += 1.0",
        "RATE, other = 0.5, 1",
        "RATE = other = 0.5",
        "for RATE in xs:\n    pass",
        "with cm() as RATE:\n    pass",
        "import RATE",
        "from m import x as RATE",
        "def RATE():\n    pass",
        "class RATE:\n    pass",
        "def f(RATE):\n    pass",
        "def f(*, RATE=0.5):\n    pass",
        "lambda RATE: 0",
        "[0 for RATE in xs]",
        "(RATE := 0.5)",
        "del RATE",
        "try:\n    pass\nexcept E as RATE:\n    pass",
        "match v:\n    case [*RATE]:\n        pass",
        "match v:\n    case {**RATE}:\n        pass",
        "match v:\n    case RATE:\n        pass",
        "RATE: float",
        "def f[RATE]():\n    pass",
        "class C[**RATE]:\n    pass",
        "type Alias[*RATE] = tuple",
        "type RATE = float",
    ],
)
def test_any_other_binding_anywhere_in_the_module_makes_the_name_not_count(binding: str) -> None:
    source = "RATE = 0.5\n" + binding + "\n"

    assert "RATE" not in kinds(source)


def test_a_read_directly_in_a_class_body_is_told_apart() -> None:
    tree = ast.parse("RATE = 0.5\nclass C:\n    a = RATE\n    def f(self):\n        return RATE\n")
    found = literal_names(tree)
    reads = [node for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id == "RATE"]
    loads = [node for node in reads if isinstance(node.ctx, ast.Load)]

    assert [id(node) in found.in_class for node in loads] == [True, False]


def test_an_operator_with_a_name_bound_to_a_float_on_the_left_hands_its_right_side_over() -> None:
    source = "RATE = 0.5\ndef f(n):\n    return RATE * n\n"

    assert "return RATE * __pyct_handed__(n, RATE)" in substituted(source)


def test_a_name_read_in_a_class_body_or_bound_otherwise_is_left_as_written() -> None:
    assert "__pyct_handed__" not in substituted("RATE = 0.5\nclass C:\n    x = RATE * n\n")
    assert "__pyct_handed__" not in substituted("RATE = 0.5\nRATE = f()\ny = RATE * n\n")
    assert "__pyct_handed__" not in substituted("NAME = 'x'\ny = NAME * n\n")


def test_a_method_on_a_name_bound_to_str_literals_is_substituted() -> None:
    source = "def f(s):\n    text = 'xyz'\n    return text.find(s)\n"

    assert "return __pyct_method__(text.find, s)" in substituted(source)
    assert "__pyct_method__" not in substituted("text = 'x'\ntext = 1.5\ny = text.find(s)\n")


def test_a_star_import_may_bind_any_name_so_no_name_counts() -> None:
    assert kinds("RATE = 0.5\nTEXT = 'x'\nfrom m import *\n") == {}


@pytest.mark.parametrize(
    "source",
    [
        "class C:\n    def m(self, x=RATE):\n        pass",
        "class C:\n    f = lambda self, x=RATE: x",
        "class C:\n    @deco(RATE)\n    def m(self):\n        pass",
        "class C:\n    held = [v for v in (RATE, 2)]",
        "class C:\n    class D(Base, k=RATE):\n        pass",
    ],
)
def test_a_read_that_runs_in_a_class_s_scope_is_told_apart(source: str) -> None:
    tree = ast.parse(source)
    found = literal_names(tree)
    loads = [node for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id == "RATE"]

    assert [id(node) in found.in_class for node in loads] == [True]


def test_a_read_in_a_method_s_or_a_lambda_s_body_is_not_in_the_class_s_scope() -> None:
    tree = ast.parse("class C:\n    f = lambda self: RATE\n    def m(self):\n        return RATE\n")
    found = literal_names(tree)
    loads = [node for node in ast.walk(tree) if isinstance(node, ast.Name) and node.id == "RATE"]

    assert [id(node) in found.in_class for node in loads] == [False, False]


def _steps_run(source: str) -> int:
    """How many loop steps the constants module takes to read the source: the work it does.

    Each pass of a loop jumps back, so jumps count the passes, a generator's inside one line
    included. Counted through a ``sys.monitoring`` tool of its own, so the tracer that measures
    the suite's coverage keeps running.
    """
    tree = ast.parse(source)
    monitoring = sys.monitoring
    tool = next(tool for tool in (3, 4, 5) if monitoring.get_tool(tool) is None)
    counted = 0

    def on_jump(code: types.CodeType, offset: int, destination: int) -> object:
        nonlocal counted
        if code.co_filename != constants.__file__:
            return monitoring.DISABLE
        counted += 1
        return None

    monitoring.use_tool_id(tool, "work count")
    monitoring.register_callback(tool, monitoring.events.JUMP, on_jump)
    monitoring.set_events(tool, monitoring.events.JUMP)
    try:
        literal_names(tree)
    finally:
        monitoring.set_events(tool, 0)
        monitoring.register_callback(tool, monitoring.events.JUMP, None)
        monitoring.free_tool_id(tool)
    return counted


def test_the_work_grows_with_a_class_body_as_it_does_with_any_body() -> None:
    def class_of(statements: int) -> str:
        return "class C:\n" + "".join(f"    a{n} = RATE\n" for n in range(statements))

    small, large = _steps_run(class_of(200)), _steps_run(class_of(800))

    # four times the statements, about four times the work: one pass, not one per statement
    assert large < 4.5 * small


def bools(source: str) -> frozenset[str]:
    return literal_names(ast.parse(source)).bools


def test_a_name_bound_to_bools_alone_is_read_as_one() -> None:
    source = (
        "READY = True\n"
        "def f(flag: bool, other: 'bool', n: int, *rest: bool):\n"
        "    done = n > 0\n"
        "    kept: bool = not n\n"
        "    (seen := n < 1)\n"
        "    made = bool(n)\n"
    )

    # a gathered parameter holds a tuple or a dict, and an int parameter is no bool
    assert bools(source) == {"READY", "flag", "other", "done", "kept", "seen", "made"}


@pytest.mark.parametrize(
    "binding",
    [
        "DONE = 1",
        "DONE = f()",
        "DONE = bool(a, b)",
        "DONE = bool(x=a)",
        "DONE += True",
        "def f(DONE):\n    pass",
        "def f(DONE: int):\n    pass",
        "for DONE in xs:\n    pass",
        "def f():\n    nonlocal DONE\n    DONE = g()",
        "type DONE = int",
        "def f[DONE]():\n    pass",
        "class A:\n    global DONE\n    DONE = 3",
    ],
)
def test_any_other_binding_makes_the_name_no_bool(binding: str) -> None:
    assert "DONE" not in bools("DONE = a < b\n" + binding + "\n")


def test_a_bool_the_builtin_makes_counts_only_while_the_module_leaves_bool_alone() -> None:
    source = "def f(flag: bool, n):\n    made = bool(n)\n    done = n > 0\n"

    assert bools(source) == {"flag", "made", "done"}
    assert bools(source + "bool = int\n") == {"done"}
    assert bools("def g(bool):\n    pass\n" + source) == {"done"}


def test_a_star_import_leaves_no_name_a_bool() -> None:
    assert bools("from m import *\nDONE = a < b\n") == frozenset()
