"""The names a module binds to one kind of literal and nothing else, such as ``RATE = 0.5``.

A name counts when every binding of it anywhere in the module, in any scope,
is an assignment of a literal to that name alone: ``RATE = 0.5`` or
``TEXT: str = "xyz"``. A parameter, a loop or ``with`` target, an import, a
``def``, ``class`` or ``type`` statement, a type parameter, an ``except``
or pattern capture, an unpacking, an augmented assignment, an annotation
with no value, which makes the name a function's own, and a ``del`` of the
name each make it not count, and a ``from m import *``, which may bind any
name, makes no name in the module count. The
kinds are the literals' types, so a name bound to 0.5 in one place and to
True in another holds a float or a bool.

The rules read such a name as they read the literal: an operator with it on
the left, and a method called on it. Which value it holds when the code runs
is still read then, since a name can also be set from outside the module's
code, through ``globals()`` or another module.

The same walk finds the names a module binds to `math` alone, every binding
an ``import math`` or ``import math as m``, and the names it binds to a
function of `math` pyct routes alone, every binding a ``from math import f``
or ``from math import f as g``; ``from math import *`` binds each of those
functions under its own name. A star import from any other module makes no
such name count. A call of ``m.f(...)`` or ``g(...)`` asks for its callee
first, and the callee is still read when the code runs.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

from pyct.core.math_calls import NAMES as MATH_NAMES

# what an import of `math` binds a name to: the module, or one of its functions pyct routes
_MODULE, _FUNCTION = "module", "function"


@dataclass(frozen=True)
class Constants:
    """What a module binds only to literals: each name's kinds, and the reads a class body makes.

    A name read directly in a class body is looked up in the class's own
    namespace first, which a metaclass may make log each lookup, so a rule
    that reads the name twice leaves those reads alone.
    """

    kinds: dict[str, frozenset[type]]
    in_class: frozenset[int]
    math_modules: frozenset[str] = frozenset()
    math_functions: frozenset[str] = frozenset()

    def kind(self, node: ast.expr) -> frozenset[type] | None:
        """The kinds of literal a name read holds, or None for anything else."""
        if not isinstance(node, ast.Name) or not isinstance(node.ctx, ast.Load):
            return None
        return self.kinds.get(node.id)

    def math_function(self, callee: ast.expr) -> bool:
        """Whether a callee names a function of `math` pyct routes, through a name the module
        binds to `math` alone, ``m.sqrt``, or to such a function alone, ``sqrt``."""
        if isinstance(callee, ast.Name):
            return callee.id in self.math_functions
        if isinstance(callee, ast.Attribute) and isinstance(callee.value, ast.Name):
            return callee.attr in MATH_NAMES and callee.value.id in self.math_modules
        return False


def literal_names(tree: ast.AST) -> Constants:
    """The names the tree binds to literals alone, and the names read directly in class bodies."""
    kinds: dict[str, set[type]] = {}
    imported: dict[str, set[str]] = {}
    refused: set[str] = set()
    counted: set[int] = set()
    in_class: set[int] = set()
    stars: set[str | None] = set()
    pending: list[tuple[ast.AST, bool]] = [(tree, False)]
    while pending:
        node, classed = pending.pop()
        _math_bindings(node, imported, counted)
        _bindings(node, kinds, refused, counted)
        if _star_import(node):
            stars.add(getattr(node, "module", None))
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and classed:
            in_class.add(id(node))
        pending.extend(_scoped(node, classed))
    refused |= kinds.keys() & imported.keys()
    modules, functions = _math_names(imported, refused, stars)
    held = {name: frozenset(types) for name, types in kinds.items() if name not in refused}
    return Constants(
        kinds={} if stars else held,
        in_class=frozenset(in_class),
        math_modules=modules,
        math_functions=functions,
    )


def _math_bindings(node: ast.AST, imported: dict[str, set[str]], counted: set[int]) -> None:
    """Note what an import of `math` or of its functions binds, each name it binds counted.

    A name `math` holds that pyct does not route, `floor` or `pi` say, is
    left to the other bindings, which refuse it.
    """
    if isinstance(node, ast.Import):
        aliases = [(alias, _MODULE) for alias in node.names if alias.name == "math"]
    elif isinstance(node, ast.ImportFrom) and node.module == "math" and node.level == 0:
        aliases = [(alias, _FUNCTION) for alias in node.names if alias.name in MATH_NAMES]
        if any(alias.name == "*" for alias in node.names):
            for name in MATH_NAMES:
                imported.setdefault(name, set()).add(_FUNCTION)
    else:
        return
    for alias, kind in aliases:
        imported.setdefault(alias.asname or alias.name, set()).add(kind)
        counted.add(id(alias))


def _math_names(
    imported: dict[str, set[str]], refused: set[str], stars: set[str | None]
) -> tuple[frozenset[str], frozenset[str]]:
    """The names bound to `math` alone, and those bound to one of its functions alone.

    A star import from any module but `math` may bind any name, so none counts.
    """
    if stars - {"math"}:
        return frozenset(), frozenset()
    held = {name: kinds for name, kinds in imported.items() if name not in refused}
    modules = frozenset(name for name, kinds in held.items() if kinds == {_MODULE})
    return modules, frozenset(name for name, kinds in held.items() if kinds == {_FUNCTION})


def _scoped(parent: ast.AST, classed: bool) -> list[tuple[ast.AST, bool]]:
    """Each child of a node, with whether it runs in a class body's scope.

    A class's body does. A function's or a lambda's body does not, while its
    decorators, defaults and annotations run where the function is written,
    so they keep the parent's scope, as does everything else. A comprehension
    in a class body is treated as the class's scope throughout, though only
    its first iterable runs there. The body is told apart by one set of its
    statements, so each child costs one lookup.
    """
    children = list(ast.iter_child_nodes(parent))
    if isinstance(parent, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
        body = {id(statement) for statement in parent.body}
        # a class's body runs in the class's scope, a function's in its own
        in_body = isinstance(parent, ast.ClassDef)
        return [(child, in_body if id(child) in body else classed) for child in children]
    if isinstance(parent, ast.Lambda):
        return [(child, classed and child is not parent.body) for child in children]
    return [(child, classed) for child in children]


def _star_import(node: ast.AST) -> bool:
    """Whether a node is ``from m import *``, which may bind any name."""
    return isinstance(node, ast.ImportFrom) and any(alias.name == "*" for alias in node.names)


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
    if isinstance(node, ast.TypeVar | ast.ParamSpec | ast.TypeVarTuple):
        return [node.name]
    if isinstance(node, ast.alias):
        return [(node.asname or node.name).partition(".")[0]]
    named = getattr(node, "name", None) if isinstance(node, _CAPTURES) else None
    rest = getattr(node, "rest", None) if isinstance(node, ast.MatchMapping) else None
    return [each for each in (named, rest) if isinstance(each, str)]


# the nodes that capture a value under a name of their own
_CAPTURES = (ast.ExceptHandler, ast.MatchAs, ast.MatchStar)
