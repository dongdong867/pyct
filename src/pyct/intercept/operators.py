"""The operators pyct substitutes where the target writes them: a float or bool literal on the left.

Python asks the left operand of an operator first, and a float or a bool
answers plainly when a tracked int or bool is on the right, so that value is
never asked and its condition is lost: `0.5 + n`, `2.5 < n`, `True & b`.

The shapes substituted are a binary operation written ``a op b``, with one
of `+ - * / // % ** << >> & | ^`, and a compare written ``a op b`` with one
of `< <= > >= == !=` alone, whose left side is a float or bool literal, or
what CPython folds to one, such as ``-0.5``, and whose right side is not
one CPython folds to a constant or a display, a comprehension, an f-string
or a lambda, which are never tracked. Nothing else is: not ``x op= n``, not
a chained compare, and no operator with any other left side, so plain code
runs as written.

The right side becomes ``__pyct_handed__(b, a)``, the literal written again
after it, and the operator itself stays Python's own
(`pyct.core.handed`). The right side is the operation's own node, moved into
the call, so it is evaluated once and in Python's order; the literal has
nothing to evaluate. The name, the literal again and the call sit where the
literal does, where CPython puts the operator's own instruction, so they add
no line.
"""

from __future__ import annotations

import ast
from typing import cast

from pyct.intercept.positions import Parts

BOUND: dict[str, str] = {"__pyct_handed__": "handed"}

_OPERATORS = (
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    ast.LShift,
    ast.RShift,
    ast.BitAnd,
    ast.BitOr,
    ast.BitXor,
)
_COMPARES = (ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.Eq, ast.NotEq)

# what the code writes that is never a tracked value
_NEVER = (
    ast.JoinedStr,
    ast.List,
    ast.Tuple,
    ast.Set,
    ast.Dict,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
    ast.Lambda,
)


def replaced(node: ast.AST, parts: Parts) -> ast.AST | None:
    """The operation with its right side handed over, or None when the rule does not take it.

    ``parts`` knows which parts of the tree CPython folds.
    """
    operands = _operands(node)
    if operands is None:
        return None
    left, right = operands
    literal = parts.folded(left)
    if literal is None or type(literal[0]) not in (float, bool):
        return None
    if isinstance(right, _NEVER) or parts.folded(right) is not None:
        return None
    again = ast.copy_location(ast.Constant(value=cast(float, literal[0])), left)
    name = ast.copy_location(ast.Name(id="__pyct_handed__", ctx=ast.Load()), left)
    handed = ast.copy_location(ast.Call(func=name, args=[right, again], keywords=[]), left)
    if isinstance(node, ast.BinOp):
        node.right = handed
    else:
        node.comparators[0] = handed  # pyrefly: ignore[missing-attribute]
    return node


def _operands(node: ast.AST) -> tuple[ast.expr, ast.expr] | None:
    """An operation's two operands, or None for a node of any other shape."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, _OPERATORS):
        return node.left, node.right
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and isinstance(node.ops[0], _COMPARES):
        return node.left, node.comparators[0]
    return None
