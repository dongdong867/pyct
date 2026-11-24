"""The subscripts pyct substitutes where the target writes them: an index read ``x[k]``.

Python's own read hashes a tracked key, or reads a tracked index as an int,
without asking it which entry it finds, so the value found loses its tie to
the input. Every subscript that reads, ``x[k]``, ``x[1, k]`` or ``x[...]``,
becomes ``__pyct_item__(x, k)`` (`pyct.core.entry.lookups.item`), the
container and the index the subscript's own nodes, moved into the call, so
each is evaluated once and in Python's order. A tuple index is the tuple
Python builds for it.

A subscript that stores, deletes or stores in place, as ``x[k] = v``,
``del x[k]`` and ``x[k] += 1``, stays as written, and so does one whose
index holds a slice, as ``x[1:2]`` and ``x[1:2, 0]``, and one CPython
folds to a constant, as ``(1, 2)[0]``, which runs no read. The parts of any
of them are substituted as anywhere else. An annotation's subscript is
never walked (`pyct.intercept.substitute`).

The call takes the subscript's position, where CPython puts its read, and
its name sits where the container's first instruction does
(`positions.Parts.named`), so it adds no line.
"""

from __future__ import annotations

import ast

from pyct.intercept.positions import Parts

_ITEM = "__pyct_item__"
BOUND: dict[str, str] = {_ITEM: "item"}
# the module the router comes from
LOOKUPS = "pyct.core.entry.lookups"


def replaced(node: ast.AST, parts: Parts) -> ast.Call | None:
    """The call that reads the item, or None when the rule does not take the node."""
    if not isinstance(node, ast.Subscript) or not isinstance(node.ctx, ast.Load):
        return None
    if _sliced(node.slice) or parts.folded(node) is not None:
        return None
    call = ast.Call(func=parts.named(_ITEM, node.value), args=[node.value, node.slice], keywords=[])
    return ast.copy_location(call, node)


def _sliced(index: ast.expr) -> bool:
    """Whether an index is a slice or a tuple that holds one, which only a subscript can write."""
    if isinstance(index, ast.Tuple):
        return any(isinstance(each, ast.Slice) for each in index.elts)
    return isinstance(index, ast.Slice)
