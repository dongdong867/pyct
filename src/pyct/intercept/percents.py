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

A str literal's ``'f' % b`` becomes ``__pyct_mod__('f', b)``, or
``__pyct_fstring_mod__('f', b)`` where ``b`` is a tuple display and CPython
compiles the `%` as the f-string it means, which this Python's compiled code
shows: the same `%` with names for operands compiles to no `%` of its own
(`pyct.core.str_formats.fstring_mod`). Any other format's ``a % (x, y)``
becomes ``__pyct_formatter__(a)((x, y))``, and ``n %= (x, y)`` becomes
``n = __pyct_in_place_formatter__(n)((x, y))``: pyct is handed the left
side first and hands back what the right side is given to, Python's own
`%` or `%=` for a left side that is not a str, so a class's own `__mod__`
or `__imod__` runs with no frame of pyct's above it. Each operand is the
operation's own node, moved into a call, so each is evaluated once and in
Python's order.

The outer call takes the operation's position, where CPython puts its own
instruction, and the name, and the call that asks for the left side, sit
where the left operand's first instruction does (`positions.Parts.named`).
So against the `%` as CPython compiles it in general, the call adds no line
of its own. Against the f-string CPython compiles for a str literal's `%`,
which builds no tuple and gives its first literal piece no position of its
own, the substituted code runs the format's line first, so the `def`
line's event at a function's start, which that piece takes, is lost, and a
tuple display spread over lines runs its first line once more, after its
items.
"""

from __future__ import annotations

import ast
import dis

from pyct.intercept.positions import Parts

_MOD = "__pyct_mod__"
_FSTRING = "__pyct_fstring_mod__"
_FORMATTER = "__pyct_formatter__"
_IN_PLACE = "__pyct_in_place_formatter__"
BOUND: dict[str, str] = {
    _MOD: "mod",
    _FSTRING: "fstring_mod",
    _FORMATTER: "formatter",
    _IN_PLACE: "in_place_formatter",
}


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
    fmt = _text(left, parts)
    if fmt is not None:
        router = _FSTRING if isinstance(right, ast.Tuple) and _an_fstring(fmt, right) else _MOD
        call = ast.Call(func=parts.named(router, left), args=[left, right], keywords=[])
        return ast.copy_location(call, node)
    if not isinstance(right, ast.Tuple):
        return None
    return _curried(_FORMATTER, left, right, node, parts)


def _augmented(node: ast.AugAssign, parts: Parts) -> ast.Assign | None:
    """``x = __pyct_in_place_formatter__(x)((a, b))`` for ``x %= (a, b)``, or None for any
    other."""
    target, right = node.target, node.value
    if not isinstance(node.op, ast.Mod) or not isinstance(target, ast.Name):
        return None
    if not isinstance(right, ast.Tuple) or parts.folded(right) is not None:
        return None
    read = ast.copy_location(ast.Name(id=target.id, ctx=ast.Load()), target)
    assignment = ast.Assign(targets=[target], value=_curried(_IN_PLACE, read, right, node, parts))
    return ast.copy_location(assignment, node)


def _curried(name: str, left: ast.expr, right: ast.expr, at: ast.AST, parts: Parts) -> ast.Call:
    """``name(left)(right)``: the call asking for the left side where the left side's first
    instruction is, and the call of what it hands back at the operation's position."""
    called = parts.named(name, left)
    asked = ast.copy_location(ast.Call(func=called, args=[left], keywords=[]), called)
    return ast.copy_location(ast.Call(func=asked, args=[right], keywords=[]), at)


def _text(node: ast.expr, parts: Parts) -> str | None:
    """The str the node is, where CPython folds it to a constant, else None."""
    folded = parts.folded(node)
    return folded[0] if folded is not None and type(folded[0]) is str else None


def _an_fstring(fmt: str, display: ast.Tuple) -> bool:
    """Whether CPython compiles ``fmt % (<this display>)`` as an f-string: whether the same `%`,
    each operand a name, compiles to no `%` of its own on this Python."""
    names: list[ast.expr] = [
        ast.Starred(value=ast.Name(id="_", ctx=ast.Load()), ctx=ast.Load())
        if isinstance(element, ast.Starred)
        else ast.Name(id="_", ctx=ast.Load())
        for element in display.elts
    ]
    held = ast.Tuple(elts=names, ctx=ast.Load())
    tree = ast.Expression(body=ast.BinOp(left=ast.Constant(value=fmt), op=ast.Mod(), right=held))
    code = compile(ast.fix_missing_locations(tree), "<format>", "eval", dont_inherit=True)
    return not any(step.opname == "BINARY_OP" for step in dis.get_instructions(code))
