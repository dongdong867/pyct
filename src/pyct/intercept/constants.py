"""The names a module binds to one kind of literal, or to bools, and nothing else.

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

The same walk reads the names bound to bools alone, which an `is` with no
constant on either side hands to pyct. Such a name's every binding in the
module is True or False, a compare, a `not`, a call of `bool` with one
argument, or a parameter annotated `bool`; the last two count only while
the module binds no name `bool` of its own. Every other binding refuses the
name as it refuses a literal one. A rich compare may answer anything, so
this reads a bool the code may not hold, and that costs one call of pyct's
on the `is` and changes no answer.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Constants:
    """What a module binds only to literals or only to bools, and the reads a class body makes.

    ``kinds`` holds each name bound to literals alone, with their types.
    ``bools`` holds each name every binding of which makes a bool as far as
    the code reads (see `_makes_a_bool`). A name read directly in a class
    body is looked up in the class's own namespace first, which a metaclass
    may make log each lookup, so a rule that reads the name twice leaves
    those reads alone.
    """

    kinds: dict[str, frozenset[type]]
    in_class: frozenset[int]
    bools: frozenset[str] = frozenset()

    def kind(self, node: ast.expr) -> frozenset[type] | None:
        """The kinds of literal a name read holds, or None for anything else."""
        if not isinstance(node, ast.Name) or not isinstance(node.ctx, ast.Load):
            return None
        return self.kinds.get(node.id)

    def holds_a_bool(self, node: ast.expr) -> bool:
        """Whether a name read is one the module binds to bools alone."""
        return (
            isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id in self.bools
        )


@dataclass
class _Bindings:
    """What the walk has seen bound: literal kinds, bools, and names refused as either."""

    kinds: dict[str, set[type]] = field(default_factory=dict)
    refused: set[str] = field(default_factory=set)
    bools: set[str] = field(default_factory=set)
    not_bools: set[str] = field(default_factory=set)
    # the bools a `bool(...)` call or a `bool` annotation makes, which the builtin must be
    by_builtin: set[str] = field(default_factory=set)
    counted: set[int] = field(default_factory=set)
    # `*args` and `**kwargs`, which hold a tuple or a dict whatever their annotation says
    gathered: set[int] = field(default_factory=set)

    def literal(self, target: ast.Name, value: object) -> None:
        """One name bound to a literal: a kind of its own, and a bool only for True or False."""
        self.kinds.setdefault(target.id, set()).add(type(value))
        self.counted.add(id(target))
        is_bool = value is True or value is False
        (self.bools if is_bool else self.not_bools).add(target.id)

    def to_bool(self, name: str, stored: ast.AST, builtin: bool) -> None:
        """One name bound to a bool that is no literal, which refuses it as a literal name."""
        self.refused.add(name)
        self.bools.add(name)
        self.counted.add(id(stored))
        if builtin:
            self.by_builtin.add(name)

    def held(self, in_class: frozenset[int]) -> Constants:
        """The names that count: a star import or a bound `bool` refuses as the docstring says."""
        kinds = {name: frozenset(types) for name, types in self.kinds.items()}
        kinds = {name: types for name, types in kinds.items() if name not in self.refused}
        refused = self.not_bools | (self.by_builtin if "bool" in self._bound() else set())
        return Constants(kinds=kinds, in_class=in_class, bools=frozenset(self.bools - refused))

    def _bound(self) -> set[str]:
        return set(self.kinds) | self.refused | self.bools


def literal_names(tree: ast.AST) -> Constants:
    """The names the tree binds to literals alone, those it binds to bools alone, and the names
    read directly in class bodies."""
    bindings = _Bindings()
    in_class: set[int] = set()
    refused_all = False
    pending: list[tuple[ast.AST, bool]] = [(tree, False)]
    while pending:
        node, classed = pending.pop()
        _bindings(node, bindings)
        refused_all = refused_all or _star_import(node)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and classed:
            in_class.add(id(node))
        pending.extend(_scoped(node, classed))
    if refused_all:
        return Constants(kinds={}, in_class=frozenset(in_class))
    return bindings.held(frozenset(in_class))


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


def _bindings(node: ast.AST, bindings: _Bindings) -> None:
    """Note what one node binds: a literal to one name, a bool to one name, or anything else.

    The name a literal or bool binding stores is noted as counted, so the
    walk does not refuse it when it reaches that name below the assignment.
    """
    if isinstance(node, ast.arguments):
        bindings.gathered.update(id(each) for each in (node.vararg, node.kwarg) if each)
    literal = _literal_binding(node)
    gathered = id(node) in bindings.gathered
    made = None if literal is not None or gathered else _bool_binding(node)
    if literal is not None:
        bindings.literal(*literal)
    elif made is not None:
        bindings.to_bool(*made)
    elif id(node) not in bindings.counted:
        names = _other_bindings(node)
        bindings.refused.update(names)
        bindings.not_bools.update(names)


def _bool_binding(node: ast.AST) -> tuple[str, ast.AST, bool] | None:
    """The name a node binds to a bool, the node that stores it, and whether the builtin `bool`
    makes it; None for any other node.

    A parameter annotated `bool`, and one name assigned, plainly, with an
    annotation or by walrus, a compare, a `not` or a `bool(...)` call.
    """
    if isinstance(node, ast.arg):
        return (node.arg, node, True) if _annotated_bool(node.annotation) else None
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target, value = node.targets[0], node.value
    elif isinstance(node, ast.AnnAssign | ast.NamedExpr) and node.value is not None:
        target, value = node.target, node.value
    else:
        return None
    made = _makes_a_bool(value)
    if not isinstance(target, ast.Name) or made is None:
        return None
    return target.id, target, made


def _makes_a_bool(value: ast.expr) -> bool | None:
    """Whether the value is read as a bool: None for one that is not, and whether the builtin
    `bool` makes it.

    A compare and a `not` are read as a bool, and a call of the name `bool`
    with one argument. A rich compare may answer anything, a numpy array
    say, and a misread costs one of pyct's calls on an `is` and changes no
    answer: `is_` answers Python's own identity for anything but two
    tracked bools.
    """
    if isinstance(value, ast.Compare) or (
        isinstance(value, ast.UnaryOp) and isinstance(value.op, ast.Not)
    ):
        return False
    called = isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
    if called and value.func.id == "bool" and len(value.args) == 1 and not value.keywords:  # pyrefly: ignore[missing-attribute]
        return True
    return None


def _annotated_bool(annotation: ast.expr | None) -> bool:
    """Whether a parameter's annotation is `bool`, written or kept as text."""
    if isinstance(annotation, ast.Name):
        return annotation.id == "bool"
    return isinstance(annotation, ast.Constant) and annotation.value == "bool"


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
