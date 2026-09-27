"""The `return` statements pyct substitutes where the target writes them: a `__bool__` method's.

CPython takes only an exact bool from `__bool__`, and a tracked bool is an
int, since bool cannot be subclassed, so a method that returns one, as
``return self.v != 0`` or ``return bool(self.v)`` on a tracked value does,
raises where plain Python runs. In a function named `__bool__` written
directly in a class body, each `return` of the function's own scope hands
its value to pyct: ``return __pyct_truth__(value)``
(`pyct.core.substitutes.truth`). A `return` in a function or class nested
in the method stays as written, and a lambda there has none; the method's
own `return` still hands over what they give back. A bare `return`, and a
value CPython folds to a constant, which is never tracked, stay as written.

A value an `and`, an `or` or a conditional expression picks is what the
method returns, so each is handed over where it is written, and its fork is
recorded where `if` would test it: ``return a and b`` becomes
``return __pyct_truth__(a) and __pyct_truth__(b)``.

The value is the statement's own node, moved into the call, which takes the
value's position, so the fork is recorded at the line and column where the
value starts. The name sits where the value's first instruction does
(`positions.Parts.named`), so it adds no line.
"""

from __future__ import annotations

import ast

from pyct.intercept.positions import Parts

_NAME = "__pyct_truth__"
BOUND: dict[str, str] = {_NAME: "truth"}

# a statement whose body is a scope of its own, where a `return` is not the method's
_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def hand_over(owner: ast.ClassDef, parts: Parts) -> None:
    """Hand the value of each `return` of each `__bool__` method of the class body to pyct, in
    place."""
    for statement in owner.body:
        if isinstance(statement, ast.FunctionDef) and statement.name == "__bool__":
            for returned in _own_returns(statement):
                _handed(returned, parts)


def _own_returns(method: ast.FunctionDef) -> list[ast.Return]:
    """Each `return` of the method's own scope, and none of a function or class nested in it.

    Only statements are walked, since a `return` is one: an expression, a
    lambda among them, holds none.
    """
    found: list[ast.Return] = []
    pending: list[ast.AST] = list(method.body)
    while pending:
        node = pending.pop()
        if isinstance(node, ast.Return):
            found.append(node)
        elif not isinstance(node, _SCOPES):
            pending.extend(
                child for child in ast.iter_child_nodes(node) if not isinstance(child, ast.expr)
            )
    return found


def _handed(returned: ast.Return, parts: Parts) -> None:
    """Put each value the `return` may give back into a call of pyct's, where it stands.

    The walk keeps its own stack, so a long chain of conditional
    expressions needs no deeper Python stack than one.
    """
    pending: list[tuple[ast.AST, str, int | None]] = [(returned, "value", None)]
    while pending:
        parent, field, index = pending.pop()
        held = getattr(parent, field)
        node = held if index is None else held[index]
        if isinstance(node, ast.BoolOp):
            pending.extend((node, "values", at) for at in range(len(node.values)))
        elif isinstance(node, ast.IfExp):
            pending.extend([(node, "body", None), (node, "orelse", None)])
        elif node is not None and parts.folded(node) is None:
            call = ast.Call(func=parts.named(_NAME, node), args=[node], keywords=[])
            call = ast.copy_location(call, node)
            if index is None:
                setattr(parent, field, call)
            else:
                held[index] = call
