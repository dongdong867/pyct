"""The hooks around each loop and comprehension assignment of a function, with the pieces switch
on: where they go, which pieces stay as written, and that the code still lines up and behaves
as written."""

import ast
import asyncio
import contextlib
from collections.abc import AsyncIterator, Callable, Iterator

import pytest

from pyct.core.entry import substitutes
from pyct.intercept.compiled import substituted_code
from pyct.intercept.substitute import substitute
from pyct.results.pieces import pieces
from tests.unit.intercept.lines_up import lined_up
from tests.unit.intercept.loop_shapes import ASSIGNMENTS, LOOPS
from tests.unit.intercept.test_substitute import BINDING

SHAPES = {**LOOPS, **{f"assign {name}": source for name, source in ASSIGNMENTS.items()}}
# the whiles left as written, by shape: each ends another loop's body, directly or through an
# `if`, its test's false outcome lands on more than one line or on none, or its test is a chained
# compare
LEFT = {
    "while_last_in_for": {(3, 8)},
    "while_last_in_while": {(4, 8)},
    "while_last_in_if_in_for": {(4, 12)},
    "while_chained": {(2, 4)},
    "while_and_last_in_if_in_for": {(5, 12)},
    "while_last_in_elif_in_with": {(7, 16)},
    "while_and_last_in_if_in_try": {(4, 12)},
    "while_or_last_in_if_in_try": {(4, 12)},
}
# the whiles whose false outcome lands on more than one line on some Python releases alone
VARIES = {
    "while_last_in_elif_in_with": {(7, 16)},
    "while_and_last_in_if_in_try": {(4, 12)},
    "while_or_last_in_if_in_try": {(4, 12)},
}
# the names of the hooks a substituted module calls
HOOKS = ("__pyct_piece_over__", "__pyct_piece_in__", "__pyct_piece_out__", "__pyct_piece_value__")


def hooked(source: str) -> str:
    """The source with the switch on, written back as Python, less its binding import."""
    lines = ast.unparse(substitute(ast.parse(source), pieces=True)).splitlines()
    return "\n".join(line for line in lines if not line.startswith(BINDING)).lstrip("\n")


def piece_sites(source: str) -> set[tuple[int, int]]:
    """The site of each piece of each function the source defines."""
    tree = ast.parse(source)
    functions = [
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    return {(piece.line, piece.col) for function in functions for _, piece in pieces(function)}


def entered(tree: ast.AST) -> set[tuple[int, int]]:
    """The site each entry hook in the tree is given."""
    return {
        (node.args[-4].value, node.args[-3].value)  # pyrefly: ignore[missing-attribute]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in ("__pyct_piece_over__", "__pyct_piece_in__")
    }


@pytest.mark.parametrize("shape", SHAPES)
def test_each_shape_lines_up_with_its_hooks(shape: str) -> None:
    source = SHAPES[shape]
    tree = substitute(ast.parse(source), pieces=True)

    expected = piece_sites(source) - LEFT.get(shape, set())
    assert lined_up(source, "<f>", pieces=True)
    assert expected <= entered(tree) <= expected | VARIES.get(shape, set())


@pytest.mark.parametrize("shape", SHAPES)
def test_with_the_switch_off_no_shape_gets_a_hook(shape: str) -> None:
    source = SHAPES[shape]

    off = ast.dump(substitute(ast.parse(source)))

    assert off == ast.dump(substitute(ast.parse(source), pieces=False))
    assert not any(name in off for name in HOOKS)


def test_a_piece_that_changes_no_name_read_later_stays_as_written() -> None:
    unchanged = (
        "def f(xs, s):\n    for x in xs:\n        g(x)\n"
        "    while s:\n        s.pop()\n    return 0\n"
    )
    changing = "def f(xs):\n    t = 0\n    for x in xs:\n        t += x\n    return t\n"

    on = ast.dump(substitute(ast.parse(unchanged), pieces=True))

    assert on == ast.dump(substitute(ast.parse(unchanged), pieces=False))
    assert "__pyct_piece_over__(xs, 3, 4, ('t', 'xs'), ('t',))" in hooked(changing)


def test_a_for_hands_its_iterable_over_and_ends_in_its_else_and_at_each_break() -> None:
    assert hooked(LOOPS["for_else_break"]) == (
        "def f(xs):\n"
        "    for x in __pyct_piece_over__(xs, 2, 4, ('xs',), ('x',)):\n"
        "        if x == 3:\n"
        "            __pyct_piece_out__(2, 4, ('xs',), ('x',))\n"
        "            break\n"
        "    else:\n"
        "        __pyct_piece_out__(2, 4, ('xs',), ('x',))\n"
        "        x = None\n"
        "    return x"
    )


def test_a_while_starts_before_its_test_and_a_while_true_ends_at_its_breaks_alone() -> None:
    assert hooked(LOOPS["while"]) == (
        "def f(n):\n"
        "    i = 0\n"
        "    __pyct_piece_in__(3, 4, ('i', 'n'), ('i',))\n"
        "    while i < n:\n"
        "        i += 1\n"
        "    else:\n"
        "        __pyct_piece_out__(3, 4, ('i', 'n'), ('i',))\n"
        "    return i"
    )
    assert hooked(LOOPS["while_true_break"]).count("__pyct_piece_out__") == 1


def test_an_assignment_hands_its_value_to_the_exit_after_the_entry_s_token() -> None:
    assert hooked(ASSIGNMENTS["listcomp"]) == (
        "def f(s):\n"
        "    u = __pyct_piece_value__(__pyct_piece_in__(2, 8, ('s',), ('u',)), "
        "[c for c in s if c])\n"
        "    return u"
    )


def test_the_call_watch_leaves_the_hooks_alone_and_watches_what_they_hold() -> None:
    source = "def f(xs):\n    for x in g(xs):\n        h(x)\n    return x\n"

    text = hooked(source)

    assert text.startswith(
        "def f(xs):\n    for x in __pyct_piece_over__(__pyct_answer__(__pyct_called__(g)("
    )
    assert not any(f"__pyct_called__({name})" in text for name in HOOKS)


def test_the_hooks_are_bound_by_the_module_and_by_each_class_body() -> None:
    source = (
        "class C:\n    def f(self, xs):\n        for x in xs:\n            pass\n        return x\n"
    )

    text = ast.unparse(substitute(ast.parse(source), pieces=True))

    assert f"{BINDING}piece_over as __pyct_piece_over__, piece_out as __pyct_piece_out__" in text
    assert "global __pyct_piece_over__, __pyct_piece_out__" in text


# a run of one shape: what it gave back or raised, and each hook call with the site it was given
type Run = tuple[object, list[tuple[str, int, int]]]


@contextlib.contextmanager
def recording(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[tuple[str, int, int]]]:
    """Each call of a hook, by its kind and the site it is given, while the block lasts."""
    calls: list[tuple[str, int, int]] = []

    def over(iterable: object, line: int, col: int, *_: object) -> object:
        calls.append(("over", line, col))
        return iterable

    def entry(line: int, col: int, *_: object) -> object:
        calls.append(("in", line, col))
        return (line, col)

    def out(line: int, col: int, *_: object) -> None:
        calls.append(("out", line, col))

    def value(token: tuple[int, int], held: object) -> object:
        calls.append(("value", *token))
        return held

    for name, hook in (("piece_over", over), ("piece_in", entry), ("piece_out", out)):
        monkeypatch.setattr(substitutes, name, hook)
    monkeypatch.setattr(substitutes, "piece_value", value)
    yield calls


def run(source: str, args: tuple[object, ...], *, pieces: bool) -> object:
    """What the shape's `f` gives back for the arguments, or the type and text of what it raises;
    a coroutine is run, and a generator read to its end."""
    namespace: dict[str, object] = {
        "g": lambda *_: None,
        "h": lambda *_: None,
        "cm": contextlib.nullcontext,
        "E": LookupError,
    }
    exec(substituted_code(source.encode(), "<shape>", pieces=pieces), namespace)  # noqa: S102
    function = namespace["f"]
    assert isinstance(function, Callable)
    try:
        answer = function(*args)
        if asyncio.iscoroutine(answer):
            return asyncio.run(answer)
        return list(answer) if isinstance(answer, Iterator) else answer
    except Exception as error:
        return type(error), str(error)


async def _numbers(*values: int) -> AsyncIterator[int]:
    for value in values:
        yield value


# each run: the shape, its arguments, and the hooks it calls, in order, with the site each gets
RUNS = [
    pytest.param("for", ([1, 2],), [("over", 3, 4), ("out", 3, 4)], id="exhausted"),
    pytest.param("for", ([],), [("over", 3, 4), ("out", 3, 4)], id="nothing to iterate"),
    pytest.param("for_else_break", ([1, 3, 5],), [("over", 2, 4), ("out", 2, 4)], id="break"),
    pytest.param("for_else_break", ([1],), [("over", 2, 4), ("out", 2, 4)], id="else"),
    pytest.param("while", (3,), [("in", 3, 4), ("out", 3, 4)], id="test false"),
    pytest.param("while", (0,), [("in", 3, 4), ("out", 3, 4)], id="never true"),
    pytest.param("while_true_break", (2,), [("in", 3, 4), ("out", 3, 4)], id="while True"),
    pytest.param("while_else_break", (0,), [("in", 2, 4), ("out", 2, 4)], id="while break"),
    pytest.param("while_else_break", (5,), [("in", 2, 4), ("out", 2, 4)], id="while else"),
    pytest.param("return_raise_in_body", ([0, 5],), [("over", 2, 4)], id="return"),
    pytest.param("return_raise_in_body", ([0, None],), [("over", 2, 4)], id="raise"),
    pytest.param("while_return_in_body", (5,), [("in", 2, 4)], id="while return"),
    pytest.param("break_in_try_finally", ([0, 1],), [("over", 2, 4), ("out", 2, 4)], id="finally"),
    pytest.param(
        "nested_break_in_else",
        ([[0, 1], [2]],),
        [("over", 3, 4), ("over", 4, 8), ("out", 4, 8), ("over", 4, 8), ("out", 4, 8)]
        + [("out", 3, 4)],
        id="nested",
    ),
    pytest.param(
        "nested_break_in_else",
        ([[0]],),
        [("over", 3, 4), ("over", 4, 8), ("out", 4, 8), ("out", 3, 4)],
        id="nested else breaks the outer",
    ),
    pytest.param(
        "generator",
        ([1, 2],),
        [("over", 3, 4), ("out", 3, 4), ("in", 6, 4), ("out", 6, 4)],
        id="generator",
    ),
    pytest.param("async_for", (_numbers(1, 2),), [("over", 3, 4), ("out", 3, 4)], id="async"),
    pytest.param("assign genexp_sum", ("abz",), [("in", 2, 11), ("value", 2, 11)], id="sum"),
    pytest.param("assign augassign", ("ab", 1), [], id="augmented, no piece"),
]


@pytest.mark.parametrize(("shape", "args", "expected"), RUNS)
def test_each_run_behaves_as_written_and_calls_each_hook_once_in_order(
    shape: str,
    args: tuple[object, ...],
    expected: list[tuple[str, int, int]],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = SHAPES[shape]
    written = run(source, args, pieces=False)
    if shape == "async_for":
        args = (_numbers(1, 2),)

    with recording(monkeypatch) as calls:
        answer = run(source, args, pieces=True)

    assert answer == written
    assert calls == expected


def test_a_loop_left_as_written_calls_no_hook(monkeypatch: pytest.MonkeyPatch) -> None:
    with recording(monkeypatch) as calls:
        answer = run(SHAPES["while_chained"], (8, 4), pieces=True)

    assert (answer, calls) == (2, [])
