"""The pieces of a function: its loops and its assignments of a comprehension, each with its site,
the names going in, the names it changes and its lines."""

import ast
import textwrap
from pathlib import Path

import pytest

from pyct.results.pieces import Piece, pieces
from tests.unit.results.test_sources import module, sources


def read(source: str) -> list[Piece]:
    """The pieces of the first function the source defines."""
    tree = ast.parse(textwrap.dedent(source))
    function = next(
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    )
    return [piece for _, piece in pieces(function)]


def names(source: str) -> list[tuple[tuple[str, ...], tuple[str, ...]]]:
    """Each piece's names going in and changed names, in the order written."""
    return [(piece.going_in, piece.changed) for piece in read(source)]


def test_a_for_loop_reads_its_iterable_and_changes_what_the_function_reads_after() -> None:
    source = """\
    def f(xs):
        t = 0
        for x in xs:
            t += x
        return t
    """

    assert read(source) == [
        Piece(line=3, col=4, going_in=("t", "x", "xs"), changed=("t",), lines=(3, 4))
    ]


def test_a_loop_variable_nothing_reads_later_is_not_a_changed_name() -> None:
    unread = "def f(xs):\n    for x in xs:\n        g(x)\n"
    read_after = "def f(xs):\n    for x in xs:\n        g(x)\n    return x\n"

    assert names(unread) == [(("x", "xs"), ())]
    assert names(read_after) == [(("x", "xs"), ("x",))]


def test_a_while_loop_reads_its_test_and_its_else_is_part_of_it() -> None:
    source = """\
    def f(n):
        i = 0
        while i < n:
            i += 1
        else:
            done = i
        return done + i
    """

    assert read(source) == [
        Piece(line=3, col=4, going_in=("i", "n"), changed=("done", "i"), lines=(3, 6))
    ]


def test_a_read_before_the_piece_counts_inside_a_loop_around_it() -> None:
    source = """\
    def f(xss):
        n = 0
        for xs in xss:
            g(n)
            for x in xs:
                n += 1
        return 0
    """

    # the outer loop reads n before the inner one on its next pass
    assert names(source) == [(("n", "xs", "xss"), ()), (("n", "xs"), ("n",))]


def test_globals_nonlocals_attributes_and_items_are_neither() -> None:
    source = """\
    def f(self, d, xs):
        global total
        for x in xs:
            total += x
            self.count += 1
            d[x] = 1
        return total, self.count, d
    """

    # the names the attribute and the item hang off are read, and nothing the loop binds is local
    assert names(source) == [(("d", "self", "x", "xs"), ())]


def test_a_nonlocal_name_is_not_the_function_s() -> None:
    source = """\
    def outer():
        c = 0
        def f(xs):
            nonlocal c
            for x in xs:
                c += x
            return c
        return f
    """
    tree = ast.parse(textwrap.dedent(source))
    inner = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "f")

    assert [(p.going_in, p.changed) for _, p in pieces(inner)] == [(("x", "xs"), ())]


def test_a_comprehension_s_own_variables_and_a_nested_function_s_names_are_not_the_function_s() -> (
    None
):
    source = """\
    def f(xs, c):
        for x in xs:
            ys = [c for c in x]
            def g(y):
                z = y + x
                return z
        return ys, g, c, z
    """

    # c inside the comprehension is its own; y and z are g's; x is read inside g and is f's
    assert names(source)[0] == (("x", "xs"), ("g", "ys"))


def test_a_name_a_comprehension_s_walrus_binds_is_the_function_s() -> None:
    source = """\
    def f(xss):
        for xs in xss:
            if any((last := v) for v in xs):
                break
        return last
    """

    assert names(source) == [(("xs", "xss"), ("last",))]


def test_a_comprehension_assignment_changes_its_target_whatever_reads_it() -> None:
    source = """\
    def f(s, z):
        t = sum(1 for c in s if c == z)
        u: list = [c for c in s]
    """

    assert read(source) == [
        Piece(line=2, col=11, going_in=("s", "z"), changed=("t",), lines=(2, 2)),
        Piece(line=3, col=14, going_in=("s",), changed=("u",), lines=(3, 3)),
    ]


def test_the_site_of_an_assignment_is_its_value_s_first_comprehension() -> None:
    source = "def f(a, b):\n    t = g([x for x in a]) + h({y for y in b})\n    return t\n"

    (piece,) = read(source)

    assert (piece.line, piece.col) == (2, 10)
    assert piece.going_in == ("a", "b")


@pytest.mark.parametrize(
    "statement",
    [
        pytest.param("a = b = [c for c in s]", id="chained"),
        pytest.param("a, b = [c for c in s]", id="unpacked"),
        pytest.param("o.a = [c for c in s]", id="an attribute"),
        pytest.param("t = len(s)", id="no comprehension"),
        pytest.param("t = lambda: [c for c in s]", id="inside a lambda"),
        pytest.param("t += sum(1 for c in s)", id="augmented"),
        pytest.param("u: list", id="no value"),
    ],
)
def test_only_an_assignment_to_one_local_name_of_a_comprehension_is_a_piece(statement: str) -> None:
    assert read(f"def f(s, o, t):\n    {statement}\n") == []


def test_an_assignment_to_a_global_is_not_a_piece() -> None:
    assert read("def f(s):\n    global t\n    t = [c for c in s]\n") == []


def test_the_pieces_of_a_function_or_class_defined_inside_are_their_own() -> None:
    source = """\
    def f(xs):
        def g(ys):
            for y in ys:
                pass
        class C:
            for z in range(3):
                pass
        while xs:
            xs = xs[1:]
        return g, C
    """

    assert [(piece.line, piece.going_in) for piece in read(source)] == [(8, ("xs",))]


def test_pieces_at_any_depth_come_in_the_order_written() -> None:
    source = """\
    async def f(xs):
        if xs:
            try:
                async for x in xs:
                    ys = [y for y in x]
            finally:
                pass
        with open(xs) as fh:
            while fh:
                break
    """

    assert [(piece.line, piece.col) for piece in read(source)] == [(4, 12), (5, 21), (9, 8)]


def test_a_piece_s_site_is_where_its_loop_source_is(tmp_path: Path) -> None:
    file = module(
        tmp_path,
        """\
        def f(s, n):
            t = 0
            for c in s:
                t += 1
            u = sum(1 for c in s if c)
            i = 0
            while i < n:
                i += 1
            if t + u + i > 9:
                return 1
            return 0
        """,
    )
    tree = ast.parse(Path(file).read_text())
    function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef))
    found = {(source.site.line, source.site.col) for source in sources(file, "f", (9, 7))}

    assert found == {(piece.line, piece.col) for _, piece in pieces(function)}


def test_each_way_a_loop_binds_a_name_changes_it() -> None:
    source = """\
    def f(xs, v):
        for x in xs:
            with open(x) as fh: pass
            try:
                pass
            except OSError as error:
                pass
            import os.path
            from json import loads as load
            class C: pass
            match v:
                case [first, *rest]:
                    pass
                case {"k": _, **others}:
                    pass
                case str() as text:
                    pass
            g = lambda y, k=x: y + k
        return fh, error, os, load, C, first, rest, others, text, g
    """

    # the lambda's default is read where it is written; its parameters are its own
    assert names(source) == [
        (
            ("v", "x", "xs"),
            ("C", "error", "fh", "first", "g", "load", "os", "others", "rest", "text"),
        )
    ]
