"""The operators pyct substitutes where the target writes them: a plain number on the left.

Python asks a plain float or bool on the left of an operator first, and it
answers plainly when a tracked int or bool is on the right, so that value is
never asked and its condition is lost: `0.5 + n`, `2.5 < n`, `True & b`.
Each binary operation, and each compare with one of the six orders and
equalities, whose left side may be a plain float or bool and whose right
side may be a tracked value, becomes a call of a function of
`pyct.core.substitutes` through a dunder name, ``__pyct_add__(a, b)`` say,
which hands the operator to the tracked value, and leaves any other pair to
Python.

The left side may be a plain float or bool unless the code writes a value
that never is one: a constant, or what CPython folds to one, of another
type, or a display, a comprehension, an f-string or a lambda. The right side
may be tracked unless the code writes one of those, or any constant. So
`n + 1` and `x == "a"` stay as written. `@` has no number to hand over.

The operands are the operation's own nodes, moved into the call, so each is
evaluated once and in Python's order. The call takes the operation's
position, where CPython puts its own instruction, and the name the left
operand's first instruction's (`positions.Parts.named`), so it adds no line.
"""

from __future__ import annotations

import ast

from pyct.intercept.positions import Parts

# the name each operator calls, and the function of pyct.core.substitutes it is bound to
_BINARY: dict[type[ast.operator], tuple[str, str]] = {
    ast.Add: ("__pyct_add__", "add"),
    ast.Sub: ("__pyct_sub__", "sub"),
    ast.Mult: ("__pyct_mul__", "mul"),
    ast.Div: ("__pyct_truediv__", "truediv"),
    ast.FloorDiv: ("__pyct_floordiv__", "floordiv"),
    ast.Mod: ("__pyct_mod__", "mod"),
    ast.Pow: ("__pyct_pow__", "power"),
    ast.LShift: ("__pyct_lshift__", "lshift"),
    ast.RShift: ("__pyct_rshift__", "rshift"),
    ast.BitAnd: ("__pyct_and__", "bit_and"),
    ast.BitOr: ("__pyct_or__", "bit_or"),
    ast.BitXor: ("__pyct_xor__", "bit_xor"),
}
_COMPARED: dict[type[ast.cmpop], tuple[str, str]] = {
    ast.Lt: ("__pyct_lt__", "lt"),
    ast.LtE: ("__pyct_le__", "le"),
    ast.Gt: ("__pyct_gt__", "gt"),
    ast.GtE: ("__pyct_ge__", "ge"),
    ast.Eq: ("__pyct_eq__", "eq"),
    ast.NotEq: ("__pyct_ne__", "ne"),
}
BOUND: dict[str, str] = dict([*_BINARY.values(), *_COMPARED.values()])

# what the code writes that is never a plain number and never a tracked value
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


def replaced(node: ast.AST, parts: Parts) -> ast.Call | None:
    """The call that replaces an operation a plain number may hand over, or None.

    ``parts`` knows which parts of the tree CPython folds, and where each starts.
    """
    operands = _operands(node)
    if operands is None:
        return None
    name, left, right = operands
    if not (_may_be_plain_number(left, parts) and _may_be_tracked(right, parts)):
        return None
    call = ast.Call(func=parts.named(name, left), args=[left, right], keywords=[])
    return ast.copy_location(call, node)


def _operands(node: ast.AST) -> tuple[str, ast.expr, ast.expr] | None:
    """The name an operation calls and its two operands, or None for any other node."""
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
        return _BINARY[type(node.op)][0], node.left, node.right
    if isinstance(node, ast.Compare) and len(node.ops) == 1 and type(node.ops[0]) in _COMPARED:
        return _COMPARED[type(node.ops[0])][0], node.left, node.comparators[0]
    return None


def _may_be_tracked(right: ast.expr, parts: Parts) -> bool:
    return not isinstance(right, _NEVER) and parts.folded(right) is None


def _may_be_plain_number(left: ast.expr, parts: Parts) -> bool:
    if isinstance(left, _NEVER):
        return False
    constant = parts.folded(left)
    return constant is None or isinstance(constant[0], float | bool)
