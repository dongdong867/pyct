"""The calls pyct substitutes where the target writes them: conversions and a str's methods.

- A call written `int(...)`, `float(...)` or `bool(...)`, bare or after a
  dot as in `builtins.int(...)`, and a call written `map(...)` with one of
  those three first, becomes ``__pyct_call__(int, ...)``. Which function
  the name holds is read when the call runs, so a name the target binds to
  its own keeps the target's meaning.
- A call written ``receiver.name(...)`` with at least one argument, where
  str has a method by that name, becomes ``__pyct_method__(receiver.name,
  ...)``. Whether the receiver is a plain str is read when the call runs.

The callee is the call's own node, moved into the call as its first
argument, and the arguments follow as written, so the callee is evaluated
first, its attribute read once, then each argument in Python's order. A call
whose arguments are written out is substituted: one with ``*`` or ``**``,
or more than `_MOST_ARGUMENTS`, stays as written, and so does a method call
whose name sits on a later line than the call starts, where CPython moves
the call's own instruction to the name's line.
"""

from __future__ import annotations

import ast

from pyct.intercept.positions import Parts

# the names whose calls are conversions pyct follows
_CONVERSIONS = frozenset({"int", "float", "bool"})
# every method a str has, which a plain str's own may be
_TEXT_METHODS = frozenset(name for name in dir(str) if not name.startswith("_"))

BOUND: dict[str, str] = {"__pyct_call__": "call", "__pyct_method__": "method"}

# the most arguments a substituted call is written with; well below CPython's 30, past which it
# builds a call's arguments in steps of its own
_MOST_ARGUMENTS = 20


def replaced(node: ast.AST, parts: Parts) -> ast.Call | None:
    """The call that replaces a conversion or a method str has, or None for any other node."""
    if not isinstance(node, ast.Call) or not _written_out(node):
        return None
    if _conversion(node):
        name = "__pyct_call__"
    elif isinstance(node.func, ast.Attribute) and node.func.attr in _TEXT_METHODS:
        name = "__pyct_method__"
    else:
        return None
    arguments = [node.func, *node.args]
    call = ast.Call(func=parts.named(name, node), args=arguments, keywords=node.keywords)
    return ast.copy_location(call, node)


def _written_out(call: ast.Call) -> bool:
    """Whether a call's arguments are written out, few, and its callee ends where it starts."""
    unpacked = any(isinstance(arg, ast.Starred) for arg in call.args) or any(
        keyword.arg is None for keyword in call.keywords
    )
    many = len(call.args) + len(call.keywords) > _MOST_ARGUMENTS
    moved = isinstance(call.func, ast.Attribute) and call.func.end_lineno != call.lineno
    return not (unpacked or many or moved) and bool(call.args or call.keywords)


def _spelled(node: ast.expr) -> str | None:
    """The name a callee is written with, bare or after a dot."""
    if isinstance(node, ast.Name):
        return node.id
    return node.attr if isinstance(node, ast.Attribute) else None


def _conversion(call: ast.Call) -> bool:
    spelled = _spelled(call.func)
    if spelled in _CONVERSIONS:
        return True
    return spelled == "map" and bool(call.args) and _spelled(call.args[0]) in _CONVERSIONS
