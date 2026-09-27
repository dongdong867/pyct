"""The calls pyct substitutes where the target writes them: conversions, `type`, `math`
functions and a str's methods.

- A call written `int(...)`, `float(...)` or `bool(...)`, bare or after a
  dot as in `builtins.int(...)`, a call written `map(...)` with one of
  those three first, a call written `type(...)` with one argument alone,
  and a call of a function of `math` that pyct routes
  (`pyct.core.math_calls.NAMES`) through a name the module binds to `math`
  or to that function alone, `math.sqrt(...)` or `root(...)` after `from
  math import sqrt as root` (`pyct.intercept.constants`), becomes
  ``__pyct_call__(int)(...)``: the callee is
  handed to pyct, which hands back pyct's router when it is Python's own
  function and the callee itself otherwise, and that is called with the
  arguments as written. So a name the target binds to its own keeps the
  target's meaning, and its function runs with no frame of pyct's above it.
  The `math` module itself is never changed.
- A call written ``"text".name(...)``, a str literal's method, with at least
  one argument, becomes ``__pyct_method__("text".name, ...)``, and so does
  one on a name every binding of which in the module is a str literal
  (`pyct.intercept.constants`).

The callee is the call's own node, moved into the new call, so it is
evaluated first, its attribute read once, then each argument in Python's
order. A call whose arguments are written out is substituted: one with
``*`` or ``**``, or with more than `_MOST_ARGUMENTS`, stays as written, and
so does a method call whose name sits on a later line than the call
starts, where CPython moves the call's own instruction to the name's line.
"""

from __future__ import annotations

import ast

from pyct.intercept.positions import Parts

# the names whose calls are conversions pyct follows
_CONVERSIONS = frozenset({"int", "float", "bool"})
# every method a str has
_TEXT_METHODS = frozenset(name for name in dir(str) if not name.startswith("_"))

BOUND: dict[str, str] = {"__pyct_call__": "call", "__pyct_method__": "method"}

# the most arguments a substituted call is written with; well below CPython's 30, past which it
# builds a call's arguments in steps of its own
_MOST_ARGUMENTS = 20


def replaced(node: ast.AST, parts: Parts) -> ast.Call | None:
    """The call that replaces a conversion, a `math` function or a str literal's method, or None
    for any other."""
    if not isinstance(node, ast.Call) or not _written_out(node):
        return None
    if _asks_for_its_callee(node) or parts.constants.math_function(node.func):
        return _curried(node, parts)
    if _text_method(node.func, parts):
        callee = parts.named("__pyct_method__", node)
        call = ast.Call(func=callee, args=[node.func, *node.args], keywords=node.keywords)
        return ast.copy_location(call, node)
    return None


def _curried(node: ast.Call, parts: Parts) -> ast.Call:
    """``__pyct_call__(callee)(...)``: pyct's call on the callee, at the callee's position."""
    name = parts.named("__pyct_call__", node)
    asked = ast.Call(func=name, args=[node.func], keywords=[])
    asked = ast.copy_location(asked, name)
    call = ast.Call(func=asked, args=node.args, keywords=node.keywords)
    return ast.copy_location(call, node)


def _written_out(call: ast.Call) -> bool:
    """Whether a call's arguments are written out, few, and its callee ends where it starts."""
    unpacked = any(isinstance(arg, ast.Starred) for arg in call.args) or any(
        keyword.arg is None for keyword in call.keywords
    )
    many = len(call.args) + len(call.keywords) > _MOST_ARGUMENTS
    moved = isinstance(call.func, ast.Attribute) and call.func.end_lineno != call.lineno
    return not (unpacked or many or moved) and bool(call.args or call.keywords)


def _text_method(callee: ast.expr, parts: Parts) -> bool:
    """Whether a callee is a method str has, on a str literal or a name bound to str literals."""
    if not isinstance(callee, ast.Attribute) or callee.attr not in _TEXT_METHODS:
        return False
    receiver = callee.value
    if isinstance(receiver, ast.Constant):
        return type(receiver.value) is str
    return parts.constants.kind(receiver) == {str}


def _spelled(node: ast.expr) -> str | None:
    """The name a callee is written with, bare or after a dot."""
    if isinstance(node, ast.Name):
        return node.id
    return node.attr if isinstance(node, ast.Attribute) else None


def _asks_for_its_callee(call: ast.Call) -> bool:
    """Whether a call is a conversion, a `map` of one or a one-argument `type`, whose callee pyct
    asks for first."""
    spelled = _spelled(call.func)
    if spelled in _CONVERSIONS:
        return True
    if spelled == "type":
        # `type` with three arguments builds a class, which pyct leaves to Python
        return len(call.args) == 1 and not call.keywords
    return spelled == "map" and bool(call.args) and _spelled(call.args[0]) in _CONVERSIONS
