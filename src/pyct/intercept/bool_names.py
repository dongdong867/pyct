"""The names a module binds to a bool alone, which a lone `a is b` hands to pyct.

Python's bools are two singletons, so two bools are the same object when
they are equal, and a tracked bool is neither of them. `pyct.intercept`
substitutes `a is b` with neither side a constant only where one operand is
a name read here as a bool: every other `is` stays Python's own, so plain
identity code, `node is not stop` or `other is self`, costs nothing more.

A name is a bool where every binding of it in the scope it is read from is
a parameter annotated `bool`, or an assignment, plain, annotated or by
walrus, of a compare, a `not`, a `bool(...)` call or the literal True or
False. A name read in a function and bound in none of its enclosing
functions is read from the module. Any other binding, a loop target, an
augmented assignment, a tuple target, an import, is not a bool, and a name
a scope declares `nonlocal` is none.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

# the nodes that open a scope of their own, and those whose body a function reads through
_FUNCTIONS = ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda
_COMPREHENSIONS = ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp


@dataclass
class _Scope:
    """One scope's bindings, each name with whether every binding of it is a bool."""

    parent: _Scope | None
    is_class: bool = False
    is_comprehension: bool = False
    bindings: dict[str, bool] = field(default_factory=dict)
    globals: set[str] = field(default_factory=set)
    nonlocals: set[str] = field(default_factory=set)

    def bind(self, name: str, is_bool: bool) -> None:
        """Note one binding: a global one goes to the module."""
        scope = self.module() if name in self.globals else self
        scope.bindings[name] = scope.bindings.get(name, True) and is_bool

    def module(self) -> _Scope:
        scope = self
        while scope.parent is not None:
            scope = scope.parent
        return scope

    def binder(self) -> _Scope:
        """Where a walrus binds: the nearest scope that is no comprehension."""
        scope = self
        while scope.is_comprehension and scope.parent is not None:
            scope = scope.parent
        return scope

    def is_bool(self, name: str) -> bool:
        """Whether the name, read here, is a bool wherever it is bound."""
        if name in self.nonlocals:
            return False
        if name in self.globals:
            return self.module().bindings.get(name, False)
        scope: _Scope | None = self
        while scope is not None:
            if name in scope.bindings:
                return scope.bindings[name]
            scope = scope.parent
            # a function reads no name of a class body it sits in
            while scope is not None and scope.is_class and scope.parent is not None:
                scope = scope.parent
        return False


def bool_names(tree: ast.Module) -> frozenset[int]:
    """The ids of the name reads in the tree that hold a bool wherever they are bound.

    The walk keeps its own stack, as the substitution's does, and reads every
    name only once the whole module is bound.
    """
    reads: list[tuple[ast.Name, _Scope]] = []
    pending: list[tuple[ast.AST, _Scope]] = [(tree, _Scope(parent=None))]
    while pending:
        node, scope = pending.pop()
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            reads.append((node, scope))
        pending.extend(_visit(node, scope))
    return frozenset(id(name) for name, scope in reads if scope.is_bool(name.id))


def _visit(node: ast.AST, scope: _Scope) -> list[tuple[ast.AST, _Scope]]:
    """Note what the node binds, and the parts left to walk, each with the scope it runs in."""
    if isinstance(node, _FUNCTIONS | ast.ClassDef):
        return _opened(node, scope)
    if isinstance(node, _COMPREHENSIONS):
        return _comprehension(node, scope)
    _bound(node, scope)
    return [(child, scope) for child in ast.iter_child_nodes(node)]


def _opened(node: ast.AST, scope: _Scope) -> list[tuple[ast.AST, _Scope]]:
    """A function or a class: its name bound where it is, its body in a scope of its own.

    Decorators, defaults, bases and annotations run in the scope around it.
    """
    inner = _Scope(parent=scope, is_class=isinstance(node, ast.ClassDef))
    if not isinstance(node, ast.Lambda):
        scope.bind(node.name, False)  # pyrefly: ignore[missing-attribute]
    outside: list[ast.AST] = list(getattr(node, "decorator_list", []))
    if isinstance(node, ast.ClassDef):
        outside += [*node.bases, *node.keywords]
        return [(part, scope) for part in outside] + [(part, inner) for part in node.body]
    arguments = node.args  # pyrefly: ignore[missing-attribute]
    outside += [each for each in (*arguments.defaults, *arguments.kw_defaults) if each]
    _declared(node, inner)
    for argument in [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]:
        inner.bind(argument.arg, _annotated_bool(argument.annotation))
    # `*args: bool` holds a tuple of bools, and `**rest: bool` a dict of them
    for gathered in (arguments.vararg, arguments.kwarg):
        if gathered is not None:
            inner.bind(gathered.arg, False)
    body = node.body  # pyrefly: ignore[missing-attribute]
    inside = body if isinstance(body, list) else [body]
    return [(part, scope) for part in outside] + [(part, inner) for part in inside]


def _comprehension(node: ast.AST, scope: _Scope) -> list[tuple[ast.AST, _Scope]]:
    """A comprehension: its first iterable in the scope around it, the rest in its own."""
    inner = _Scope(parent=scope, is_comprehension=True)
    generators: list[ast.comprehension] = node.generators  # pyrefly: ignore[missing-attribute]
    parts: list[tuple[ast.AST, _Scope]] = [(generators[0].iter, scope)]
    for index, generator in enumerate(generators):
        for part in ast.walk(generator.target):
            if isinstance(part, ast.Name):
                inner.bind(part.id, False)
        if index:
            parts.append((generator.iter, inner))
        parts += [(condition, inner) for condition in generator.ifs]
    kept = [getattr(node, name) for name in ("elt", "key", "value") if hasattr(node, name)]
    return parts + [(part, inner) for part in kept]


def _declared(function: ast.AST, scope: _Scope) -> None:
    """The names a function declares `global` or `nonlocal`, noted before any binding is.

    The walk takes a body's statements last first, so a declaration is read
    ahead of them, in the function's own body and in no scope inside it.
    """
    pending = list(ast.iter_child_nodes(function))
    while pending:
        node = pending.pop()
        if isinstance(node, ast.Global):
            scope.globals.update(node.names)
        elif isinstance(node, ast.Nonlocal):
            scope.nonlocals.update(node.names)
        elif not isinstance(node, _FUNCTIONS | ast.ClassDef | _COMPREHENSIONS):
            pending.extend(ast.iter_child_nodes(node))


def _bound(node: ast.AST, scope: _Scope) -> None:
    """Note the names one node binds, and whether each binding is a bool."""
    if isinstance(node, ast.Assign):
        for target in node.targets:
            _assigned(target, node.value, scope)
    elif isinstance(node, ast.AnnAssign) and node.value is not None:
        _assigned(node.target, node.value, scope)
    elif isinstance(node, ast.NamedExpr):
        scope.binder().bind(node.target.id, _makes_a_bool(node.value))
    elif isinstance(node, ast.Import | ast.ImportFrom):
        for alias in node.names:
            scope.bind((alias.asname or alias.name).split(".")[0], False)
    else:
        _other_binding(node, scope)


def _assigned(target: ast.expr, value: ast.expr, scope: _Scope) -> None:
    """An assignment's target: a bare name takes the value's kind, and a name in a tuple none."""
    if isinstance(target, ast.Name):
        scope.bind(target.id, _makes_a_bool(value))
    else:
        for part in ast.walk(target):
            if isinstance(part, ast.Name) and isinstance(part.ctx, ast.Store):
                scope.bind(part.id, False)


def _other_binding(node: ast.AST, scope: _Scope) -> None:
    """Every other binding a node makes, none of them a bool."""
    if isinstance(node, ast.AugAssign | ast.For | ast.AsyncFor | ast.withitem):
        target = node.target if not isinstance(node, ast.withitem) else node.optional_vars
        for part in ast.walk(target) if target is not None else ():
            if isinstance(part, ast.Name):
                scope.bind(part.id, False)
    elif isinstance(node, ast.ExceptHandler | ast.MatchAs | ast.MatchStar) and node.name:
        scope.bind(node.name, False)
    elif isinstance(node, ast.MatchMapping) and node.rest:
        scope.bind(node.rest, False)


def _makes_a_bool(value: ast.expr) -> bool:
    """Whether the value is a bool however it runs: a compare, a `not`, `bool(...)`, a literal."""
    if isinstance(value, ast.Compare):
        return True
    if isinstance(value, ast.UnaryOp):
        return isinstance(value.op, ast.Not)
    if isinstance(value, ast.Constant):
        return value.value is True or value.value is False
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id == "bool"
        and not value.keywords
    )


def _annotated_bool(annotation: ast.expr | None) -> bool:
    """Whether a parameter's annotation is `bool`, written or kept as text."""
    if isinstance(annotation, ast.Name):
        return annotation.id == "bool"
    return isinstance(annotation, ast.Constant) and annotation.value == "bool"
