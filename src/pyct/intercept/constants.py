"""The names a module binds to one kind of literal and nothing else, such as ``RATE = 0.5``.

A name counts when every binding of it anywhere in the module, in any scope,
is an assignment of a literal to that name alone: ``RATE = 0.5`` or
``TEXT: str = "xyz"``. A parameter, a loop or ``with`` target, an import, a
``def`` or ``class``, an ``except`` or pattern capture, an unpacking, an
augmented assignment, an annotation with no value, which makes the name a
function's own, and a ``del`` of the name each make it not count. The
kinds are the literals' types, so a name bound to 0.5 in one place and to
True in another holds a float or a bool.

The rules read such a name as they read the literal: an operator with it on
the left, and a method called on it. Which value it holds when the code runs
is still read then, since a name can also be set from outside the module's
code, through ``globals()`` or another module.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

# the nodes that open a scope of their own, where a name is looked up as a function looks it up
_FUNCTIONS = (
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.Lambda,
    ast.ListComp,
    ast.SetComp,
    ast.DictComp,
    ast.GeneratorExp,
)


@dataclass(frozen=True)
class Constants:
    """What a module binds only to literals: each name's kinds, and the reads a class body makes.

    A name read directly in a class body is looked up in the class's own
    namespace first, which a metaclass may make log each lookup, so a rule
    that reads the name twice leaves those reads alone.
    """

    kinds: dict[str, frozenset[type]]
    in_class: frozenset[int]

    def kind(self, node: ast.expr) -> frozenset[type] | None:
        """The kinds of literal a name read holds, or None for anything else."""
        if not isinstance(node, ast.Name) or not isinstance(node.ctx, ast.Load):
            return None
        return self.kinds.get(node.id)


def literal_names(tree: ast.AST) -> Constants:
    """The names the tree binds to literals alone, and the names read directly in class bodies."""
    kinds: dict[str, set[type]] = {}
    refused: set[str] = set()
    counted: set[int] = set()
    in_class: set[int] = set()
    pending: list[tuple[ast.AST, bool]] = [(tree, False)]
    while pending:
        node, classed = pending.pop()
        _bindings(node, kinds, refused, counted)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and classed:
            in_class.add(id(node))
        inner = isinstance(node, ast.ClassDef) or (classed and not isinstance(node, _FUNCTIONS))
        pending.extend((child, inner) for child in ast.iter_child_nodes(node))
    held = {name: frozenset(types) for name, types in kinds.items() if name not in refused}
    return Constants(kinds=held, in_class=frozenset(in_class))


def _bindings(
    node: ast.AST, kinds: dict[str, set[type]], refused: set[str], counted: set[int]
) -> None:
    """Note what one node binds: a literal to one name, or anything else to any name.

    The name a literal binding stores is noted as counted, so the walk does
    not refuse it when it reaches that name below the assignment.
    """
    literal = _literal_binding(node)
    if literal is not None:
        target, value = literal
        kinds.setdefault(target.id, set()).add(type(value))
        counted.add(id(target))
    elif id(node) not in counted:
        refused.update(_other_bindings(node))


def _literal_binding(node: ast.AST) -> tuple[ast.Name, object] | None:
    """The name and literal of ``NAME = literal`` or ``NAME: kind = literal``, else None."""
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target, value = node.targets[0], node.value
    elif isinstance(node, ast.AnnAssign) and node.value is not None:
        target, value = node.target, node.value
    else:
        return None
    if isinstance(target, ast.Name) and isinstance(value, ast.Constant):
        return target, value.value
    return None


def _other_bindings(node: ast.AST) -> list[str]:
    """The names a node binds any other way."""
    if isinstance(node, ast.Name) and not isinstance(node.ctx, ast.Load):
        return [node.id]
    if isinstance(node, ast.arg):
        return [node.arg]
    if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return [node.name]
    if isinstance(node, ast.alias):
        return [(node.asname or node.name).partition(".")[0]]
    named = getattr(node, "name", None) if isinstance(node, _CAPTURES) else None
    rest = getattr(node, "rest", None) if isinstance(node, ast.MatchMapping) else None
    return [each for each in (named, rest) if isinstance(each, str)]


# the nodes that capture a value under a name of their own
_CAPTURES = (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)
