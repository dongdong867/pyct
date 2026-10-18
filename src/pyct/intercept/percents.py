"""The `%` pyct substitutes where the target writes it: a format beside a tuple display, a str
literal's format, and a name's `%=` with a tuple display.

Python copies each operand's text into a new plain str when it formats
with `%`, and asks no method of a tracked int or of a tuple's items, so
the condition is lost there. The shapes substituted are a binary `%`
written ``<format> % (<tuple display>)``, whatever the format is, or
``<str literal> % <operand>``, whatever the operand is, the literal
being what CPython folds to a str; and an augmented assignment written
``<name> %= (<tuple display>)``. A right side CPython folds to a constant
holds nothing tracked and stays as written, and so does any other `%`.

``a % b`` becomes ``__pyct_mod__(a, b)``, and ``x %= (a, b)`` becomes
``x = __pyct_imod__(x, (a, b))``, each operand the operation's own node,
moved into the call, so each is evaluated once and in Python's order
(`pyct.core.str_formats`). The call takes the operation's position, where
CPython puts its own instruction, and the name sits where the left
operand's first instruction does (`positions.Parts.named`), so it adds no
line. Substituted, a format with a tuple display is no longer one CPython
compiles as an f-string, which it does for one of `%s`, `%r` and `%a`
alone.
"""

from __future__ import annotations

import ast

from pyct.intercept.positions import Parts

_MOD = "__pyct_mod__"
_IMOD = "__pyct_imod__"
BOUND: dict[str, str] = {_MOD: "mod", _IMOD: "imod"}


def replaced(node: ast.AST, parts: Parts) -> ast.AST | None:
    """The call that replaces a `%` or a `%=` of the shapes, or None when the rule does not take
    it."""
    if isinstance(node, ast.AugAssign):
        return _augmented(node, parts)
    if not isinstance(node, ast.BinOp) or not isinstance(node.op, ast.Mod):
        return None
    left, right = node.left, node.right
    if parts.folded(right) is not None:
        return None
    if not isinstance(right, ast.Tuple) and not _text(left, parts):
        return None
    call = ast.Call(func=parts.named(_MOD, left), args=[left, right], keywords=[])
    return ast.copy_location(call, node)


def _augmented(node: ast.AugAssign, parts: Parts) -> ast.Assign | None:
    """``x = __pyct_imod__(x, (a, b))`` for ``x %= (a, b)``, or None for any other."""
    target, right = node.target, node.value
    if not isinstance(node.op, ast.Mod) or not isinstance(target, ast.Name):
        return None
    if not isinstance(right, ast.Tuple) or parts.folded(right) is not None:
        return None
    read = ast.copy_location(ast.Name(id=target.id, ctx=ast.Load()), target)
    call = ast.Call(func=parts.named(_IMOD, target), args=[read, right], keywords=[])
    assignment = ast.Assign(targets=[target], value=ast.copy_location(call, node))
    return ast.copy_location(assignment, node)


def _text(node: ast.expr, parts: Parts) -> bool:
    """Whether the node is a str CPython folds to a constant."""
    folded = parts.folded(node)
    return folded is not None and type(folded[0]) is str
