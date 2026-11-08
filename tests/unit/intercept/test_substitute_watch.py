"""Which calls the transform watches for a lost tracked value, and how it writes them."""

import ast

import pytest

from pyct.intercept.substitute import substitute
from tests.unit.intercept.lines_up import lined_up
from tests.unit.intercept.test_substitute import BINDING, WATCH_NAMES


def watched(source: str) -> str:
    """The source as the transform leaves it, watch included, less its binding import."""
    lines = ast.unparse(substitute(ast.parse(source))).splitlines()
    return "\n".join(line for line in lines if not line.startswith(BINDING))


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("bin(x)", "__pyct_answer__(bin(__pyct_first__(x)), 'bin')"),
        ("f(a, b)", "__pyct_answer__(f(__pyct_first__(a), __pyct_given__(b)), 'f')"),
        ("f(a, 1)", "__pyct_answer__(f(__pyct_first__(a), 1), 'f')"),
        ("f(1, a)", "__pyct_answer__(f(__pyct_first__(1), __pyct_given__(a)), 'f')"),
        ("f(a, k=b)", "__pyct_answer__(f(__pyct_first__(a), k=__pyct_given__(b)), 'f')"),
        (
            "math.factorial(n)",
            "__pyct_answer__(math.factorial(__pyct_first__(n)), 'math.factorial')",
        ),
        ("self.parse(s)", "__pyct_answer__(self.parse(__pyct_first__(s)), 'self.parse')"),
        (
            "f(g(x))",
            "__pyct_answer__(f(__pyct_first__(__pyct_answer__(g(__pyct_first__(x)), 'g'))), 'f')",
        ),
    ],
)
def test_a_call_with_an_argument_is_watched_under_the_name_it_is_written_with(
    source: str, expected: str
) -> None:
    assert watched(source) == expected


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("f()", id="no argument"),
        pytest.param("f(1, 'a')", id="constants alone"),
        pytest.param("f(*xs)", id="unpacked by position"),
        pytest.param("f(**kw)", id="unpacked by keyword"),
        pytest.param("isinstance(x, int)", id="a type check"),
        pytest.param("callable(x)", id="callable"),
        pytest.param("hasattr(x, 'a')", id="hasattr"),
        pytest.param("len(s)", id="a builtin pyct binds"),
        pytest.param("ord(c)", id="ord"),
        pytest.param("int(s)", id="a call another rule routes"),
        pytest.param("'abc'.find(s)", id="a str literal's method"),
        pytest.param("(\n x).y(z)", id="a method named on a later line"),
    ],
)
def test_a_call_pyct_routes_or_that_cannot_take_a_tracked_value_is_not_watched(
    source: str,
) -> None:
    assert not WATCH_NAMES & {
        node.id for node in ast.walk(ast.parse(watched(source))) if isinstance(node, ast.Name)
    }


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("async def g():\n    return f(await h(x))", id="await"),
        pytest.param("def g():\n    return f((yield x))", id="yield"),
        pytest.param("def g():\n    return f((yield from xs))", id="yield from"),
    ],
)
def test_a_call_whose_argument_can_stop_its_frame_is_not_watched(source: str) -> None:
    assert "'f')" not in watched(source)


def test_the_call_stays_the_call_written_with_its_own_nodes() -> None:
    tree = ast.parse("f(a, b)")
    call = tree.body[0].value  # pyrefly: ignore[missing-attribute]
    callee = call.func

    substitute(tree)

    outer = tree.body[-1].value  # pyrefly: ignore[missing-attribute]
    assert outer.args[0] is call
    assert call.func is callee


@pytest.mark.parametrize(
    "source",
    [
        "f(a,\n  b or c)",
        "f(\n a or b)",
        "f(a or b,\n c)",
        "f(\n a if t else\n b, c)",
        "f(a,\n b < c < d)",
        "f(x=a or b,\n y=c)",
        "g(h(\n a=1,\n b=k and 2))",
        "f('''a\n'''.format(x),\n 2)",
        "f(a,\n [g(m or 1,\n 2) for m in y])",
    ],
)
def test_a_watched_call_spread_over_lines_lines_up(source: str) -> None:
    indented = source.replace("\n", "\n    ")
    assert lined_up(f"def _f():\n    {indented}\n", "<f>")
