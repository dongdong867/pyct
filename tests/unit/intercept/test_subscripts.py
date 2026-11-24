"""Which subscripts the transform hands to pyct: each index read ``x[k]``, at its own position,
and no slice, store, delete, augmented store or annotation."""

import ast

import pytest

from pyct.intercept.substitute import substitute
from tests.unit.intercept.lines_up import layout


def substituted(source: str) -> str:
    """The substituted module written back as Python, without the import of pyct's names."""
    tree = substitute(ast.parse(source))
    return ast.unparse([each for each in tree.body if not isinstance(each, ast.ImportFrom)])


def read_spans(tree: ast.AST) -> set[tuple[int, int, int | None, int | None]]:
    """Where each index read of the tree as written is."""
    return {
        (node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load)
    }


def item_calls(tree: ast.AST) -> list[ast.Call]:
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "__pyct_item__"
    ]


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("y = x[k]", "y = __pyct_item__(x, k)"),
        ("y = a.b[k]", "y = __pyct_item__(a.b, k)"),
        ("y = x[k][j]", "y = __pyct_item__(__pyct_item__(x, k), j)"),
        ("y = x[1, k]", "y = __pyct_item__(x, (1, k))"),
        ("y = x[*k]", "y = __pyct_item__(x, (*k,))"),
        ("y = x[...]", "y = __pyct_item__(x, ...)"),
        ("y = 'abc'[n]", "y = __pyct_item__('abc', n)"),
        ("y = x[k] in z", "y = __pyct_in__(__pyct_item__(x, k), z)"),
        ("x[y[k]] = 1", "x[__pyct_item__(y, k)] = 1"),
        # spread over lines: the name where the container's first instruction is, the call where
        # CPython read the item
        ("y = (\n    x)[k]", "y = __pyct_item__(x, k)"),
        ("y = x[\n    k]", "y = __pyct_item__(x, k)"),
        ("y = (x\n    .w)[k]", "y = __pyct_item__(x.w, k)"),
        ("y = (x[k] +\n    z[j])", "y = __pyct_item__(x, k) + __pyct_item__(z, j)"),
    ],
)
def test_an_index_read_becomes_a_call_at_its_position(source: str, expected: str) -> None:
    function = f"def f():\n{''.join(f'    {line}\n' for line in source.splitlines())}"
    tree = substitute(ast.parse(function))
    calls = item_calls(tree)

    assert substituted(function) == f"def f():\n    {expected}"
    assert {
        (call.lineno, call.col_offset, call.end_lineno, call.end_col_offset) for call in calls
    } == read_spans(ast.parse(function))
    for call in calls:
        value = call.args[0]
        while isinstance(value, ast.Call | ast.Attribute):
            value = value.args[0] if isinstance(value, ast.Call) else value.value
        assert isinstance(call.func, ast.Name)
        assert (call.func.lineno, call.func.col_offset) == (value.lineno, value.col_offset)
    assert layout(compile(function, "<m>", "exec")) == layout(compile(tree, "<m>", "exec"))


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        # a slice, bare or beside an item, and its bounds' own reads
        ("z = x[1:2] + y[j]", "z = x[1:2] + __pyct_item__(y, j)"),
        ("z = x[a:y[j]]", "z = x[a:__pyct_item__(y, j)]"),
        ("z = x[1:2, y[j]]", "z = x[1:2, __pyct_item__(y, j)]"),
        ("z = x[::2]", "z = x[::2]"),
        # a store, a delete and an augmented store, whose index's own reads are substituted
        ("x[k] = y[j]", "x[k] = __pyct_item__(y, j)"),
        ("x[k], w = y[j], 1", "x[k], w = (__pyct_item__(y, j), 1)"),
        ("del x[y[j]]", "del x[__pyct_item__(y, j)]"),
        ("x[k] += y[j]", "x[k] += __pyct_item__(y, j)"),
        ("for x[k] in y[j]:\n    pass", "for x[k] in __pyct_item__(y, j):\n    pass"),
        # a read CPython folds to one constant, which runs no read
        ("z = (1, 2)[0] + y[j]", "z = (1, 2)[0] + __pyct_item__(y, j)"),
    ],
)
def test_a_slice_a_store_a_delete_and_an_augmented_store_stay_as_written(
    source: str, expected: str
) -> None:
    assert substituted(source) == expected


def test_an_annotation_s_subscript_stays_as_written() -> None:
    source = (
        "def f(x: list[int], *rest: tuple[str, ...]) -> dict[str, int]:\n"
        "    y: tuple[int, ...] = x[0]\n"
        "    return y\n"
    )

    assert substituted(source) == (
        "def f(x: list[int], *rest: tuple[str, ...]) -> dict[str, int]:\n"
        "    y: tuple[int, ...] = __pyct_item__(x, 0)\n"
        "    return y"
    )
