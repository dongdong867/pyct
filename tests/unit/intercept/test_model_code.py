"""Model-written code compiles under the target's substitutions, in the form a tool's check allows,
and nothing of it runs while it compiles."""

import ast
import types

import pytest

from pyct.execution.blame import one_line
from pyct.execution.execute import ExecutionContext, execute
from pyct.intercept.model_code import Refused, compile_model_code
from pyct.intercept.wrap import bound_builtins

FILE = "<model m:2:7>"

ANY_FORM = lambda tree: tree  # noqa: E731 - a check that takes every tree as it is


def function(code: types.CodeType, name: str) -> types.FunctionType:
    """The function the code defines, its module run in a namespace of its own, as a child of
    pyct's process runs it."""
    namespace: dict[str, object] = {"__builtins__": bound_builtins()}
    exec(code, namespace)
    made = namespace[name]
    assert isinstance(made, types.FunctionType)
    return made


def test_an_accepted_function_called_on_bound_leaves_forks_in_its_parameters_names() -> None:
    code = compile_model_code(
        "def f(n):\n    if n > 3:\n        return 1\n    return 0\n", FILE, ANY_FORM
    )
    assert isinstance(code, types.CodeType)

    executed = execute(ExecutionContext(fn=function(code, "f"), file=FILE), {"n": 5})

    assert [(fork.expression, fork.taken) for fork in executed.branches] == [([">", "n", 3], True)]
    assert executed.branches[0].site.file == FILE


def test_the_code_takes_the_target_s_substitutions() -> None:
    # Python asks the literal whether it holds the str, which no tracked value hears
    text = "def f(s):\n    if s in 'abc':\n        return 1\n    return 0\n"
    code = compile_model_code(text, FILE, ANY_FORM)
    assert isinstance(code, types.CodeType)

    executed = execute(ExecutionContext(fn=function(code, "f"), file=FILE), {"s": "b"})

    assert executed.failure is None
    assert [fork.taken for fork in executed.branches] == [True]


def test_the_check_s_tree_is_the_one_compiled() -> None:
    def negated(tree: ast.Module) -> ast.Module:
        (made,) = tree.body
        assert isinstance(made, ast.FunctionDef)
        (answer,) = made.body
        assert isinstance(answer, ast.Return) and answer.value is not None
        answer.value = ast.UnaryOp(ast.Not(), answer.value)
        return tree

    code = compile_model_code("def f(n):\n    return n > 3\n", FILE, negated)
    assert isinstance(code, types.CodeType)

    assert function(code, "f")(5) is False


def test_a_tree_the_check_refuses_gives_the_check_s_reason() -> None:
    def no_loops(tree: ast.Module) -> ast.Module | str:
        loops = [node for node in ast.walk(tree) if isinstance(node, ast.For | ast.While)]
        return "a loop at line 2" if loops else tree

    refused = compile_model_code("def f(s):\n    for c in s:\n        pass\n", FILE, no_loops)

    assert refused == Refused("a loop at line 2")


@pytest.mark.parametrize(
    "text",
    [
        "def f(:\n    return 1\n",
        "def f(x):\n    return x\0\n",
        # too deep for the parser, as a long reply can be
        "def f(x):\n    return " + "-" * 20_000 + "x\n",
    ],
)
def test_text_that_does_not_parse_gives_the_parser_s_reason(text: str) -> None:
    try:
        ast.parse(text, filename=FILE)
    except (SyntaxError, ValueError, RecursionError, MemoryError) as error:
        said = one_line(error)
    else:
        raise AssertionError("the text parses")

    assert compile_model_code(text, FILE, ANY_FORM) == Refused(f"does not parse: {said}")


def test_a_tree_that_does_not_compile_gives_the_compiler_s_reason() -> None:
    text = "def f(x):\n    nonlocal x\n    return x\n"
    with pytest.raises(SyntaxError) as plain:
        compile(text, FILE, "exec", dont_inherit=True)

    refused = compile_model_code(text, FILE, ANY_FORM)

    assert refused == Refused(f"does not compile: {one_line(plain.value)}")


def test_nothing_runs_while_the_code_compiles() -> None:
    text = "raise SystemExit('ran')\ndef f():\n    return 1\n"

    code = compile_model_code(text, FILE, ANY_FORM)

    assert isinstance(code, types.CodeType)
