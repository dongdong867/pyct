"""The pieces of a function pyct can record: its loops, and its assignments of a comprehension.

A piece is a ``for``, ``async for`` or ``while`` statement of a function's
own body, at any depth, or an assignment there to one local name of the
function's, with or without an annotation, whose value holds a list, set or
dict comprehension or a generator expression outside any lambda. A function
or class defined inside the function has a body of its own. Each piece is
read off the function's AST, without running it:

- its site: a loop's first keyword, and an assignment's first comprehension
  in the order written, which is where `pyct.results.sources` places a loop
  source, so a condition's loop source names the piece it came from;
- the names going in: the function's local names, its parameters among
  them, that the piece reads, less a ``for`` loop's own variables, which
  it binds before its body reads them, unless its iterable reads them;
- the changed names: for a loop, the function's local names it binds that
  the function reads anywhere outside the loop, a loop around it included;
  for an assignment, its target;
- its first and last line.

A function's local names are its parameters and the names its own code
binds: by an assignment, an augmented one, which reads its name too, a
``for`` target, a ``with`` or ``except`` name, an import, a ``def`` or
``class``, a ``match`` capture, or a ``:=``, one inside a comprehension
included. A name it declares ``global`` or ``nonlocal`` is not one. A name
read inside a comprehension, a lambda, or a function or class defined in
the function is the function's when no such scope around the read binds it:
a comprehension's own variables, and a nested scope's parameters, names and
``global`` declarations. An annotation is not read.
"""

from __future__ import annotations

import ast
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field

from pyct.results.sources import COMPREHENSIONS, LOOPS, names_in

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
_SCOPES = (*_FUNCTIONS, ast.Lambda, ast.ClassDef)

type Function = ast.FunctionDef | ast.AsyncFunctionDef
# a scope a function holds, each with a body of its own
type _Scope = ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda | ast.ClassDef
# one name the walk meets in the function's own scope: whether it is bound there, else read,
# the name, and the node it is met at
type _Met = tuple[bool, str, ast.AST]
# a node to walk, with the names the scopes around it bind, and those its nested scopes bind,
# which a `:=` in a comprehension does not see past
type _Pending = tuple[ast.AST, frozenset[str], frozenset[str]]


@dataclass(frozen=True)
class Piece:
    """A piece's site, its names going in and changed names, each sorted, and its first and last
    line."""

    line: int
    col: int
    going_in: tuple[str, ...]
    changed: tuple[str, ...]
    lines: tuple[int, int]


def pieces(function: Function) -> list[tuple[ast.stmt, Piece]]:
    """Each piece of the function, with its statement, in the order written."""
    walk = _Walk()
    local = walk.locals_of(function)
    statements = [each for each in _own_statements(function) if _is_piece(each, local)]
    if not statements:
        return []
    everywhere = [(name, node) for bound, name, node in walk.met(function.body) if not bound]
    return [(each, _piece(each, walk, local, everywhere)) for each in statements]


def _piece(
    statement: ast.stmt, walk: _Walk, local: frozenset[str], everywhere: list[tuple[str, ast.AST]]
) -> Piece:
    """One piece read off its statement, given every read of the function's own scope."""
    met = list(walk.met([statement]))
    going_in = {name for bound, name, _ in met if not bound and name in local}
    going_in -= _bound_first(statement, walk)
    assigned = _assigned(statement)
    if assigned is not None:
        target, comprehension = assigned
        site = (comprehension.lineno, comprehension.col_offset)
        changed = {target.id}
    else:
        inside = {id(node) for bound, _, node in met if not bound}
        outside = {name for name, node in everywhere if id(node) not in inside}
        changed = {name for bound, name, _ in met if bound and name in local} & outside
        site = (statement.lineno, statement.col_offset)
    return Piece(
        line=site[0],
        col=site[1],
        going_in=tuple(sorted(going_in)),
        changed=tuple(sorted(changed)),
        lines=(statement.lineno, statement.end_lineno or statement.lineno),
    )


def _bound_first(statement: ast.stmt, walk: _Walk) -> set[str]:
    """The names a ``for`` binds before its body can read them: its target's, less those its
    iterable reads. Any other piece binds none first."""
    if not isinstance(statement, ast.For | ast.AsyncFor):
        return set()
    read = {name for bound, name, _ in walk.met([statement.iter]) if not bound}
    return set(names_in(statement.target)) - read


def _own_statements(function: Function) -> Iterator[ast.stmt]:
    """The statements of the function's own body at any depth, in the order written, without
    those of a scope defined inside it."""
    pending: list[ast.AST] = list(reversed(function.body))
    while pending:
        node = pending.pop()
        if isinstance(node, ast.stmt):
            yield node
        if not isinstance(node, _SCOPES):
            pending.extend(reversed(list(ast.iter_child_nodes(node))))


def _is_piece(statement: ast.stmt, local: frozenset[str]) -> bool:
    """Whether a statement of the function's own body is a loop, or an assignment to one of its
    local names whose value holds a comprehension."""
    if isinstance(statement, LOOPS):
        return True
    assigned = _assigned(statement)
    return assigned is not None and assigned[0].id in local


def _assigned(statement: ast.stmt) -> tuple[ast.Name, ast.expr] | None:
    """An assignment's one plain name and its value's first comprehension, or None for any other
    statement and an assignment of no comprehension."""
    if isinstance(statement, ast.Assign) and len(statement.targets) == 1:
        target, value = statement.targets[0], statement.value
    elif isinstance(statement, ast.AnnAssign) and statement.value is not None:
        target, value = statement.target, statement.value
    else:
        return None
    comprehension = _first_comprehension(value)
    if not isinstance(target, ast.Name) or comprehension is None:
        return None
    return target, comprehension


def _first_comprehension(value: ast.expr) -> ast.expr | None:
    """The value's first comprehension in the order written, outside any lambda, or None."""
    pending: list[ast.AST] = [value]
    while pending:
        node = pending.pop()
        if isinstance(node, COMPREHENSIONS):
            return node
        if not isinstance(node, ast.Lambda):
            pending.extend(reversed(list(ast.iter_child_nodes(node))))
    return None


@dataclass
class _Walk:
    """A walk over one function's code that meets each name it binds and reads in its own scope,
    with each nested scope's own names worked out once."""

    _own: dict[int, frozenset[str]] = field(default_factory=dict)

    def locals_of(self, function: Function) -> frozenset[str]:
        """The function's local names: its parameters and the names its own code binds, less
        those it declares global or nonlocal."""
        bound = {name for binds, name, _ in self.met(function.body) if binds}
        declared = _declared(function.body, ast.Global) | _declared(function.body, ast.Nonlocal)
        return frozenset((_parameters(function) | bound) - declared)

    def met(self, nodes: Iterable[ast.AST]) -> Iterator[_Met]:
        """Each name the nodes bind or read in the function's own scope, in the order written."""
        empty: frozenset[str] = frozenset()
        pending: list[_Pending] = [(node, empty, empty) for node in reversed(list(nodes))]
        while pending:
            node, hidden, scoped = pending.pop()
            yield from _named(node, hidden, scoped)
            pending.extend(reversed(self._inside(node, hidden, scoped)))

    def _inside(
        self, node: ast.AST, hidden: frozenset[str], scoped: frozenset[str]
    ) -> list[_Pending]:
        """The parts of a node to walk next, each with the names hidden from the function there."""
        if isinstance(node, COMPREHENSIONS):
            return _comprehension_parts(node, hidden, scoped)
        if isinstance(node, _SCOPES):
            own = self._names_of(node)
            outer: list[_Pending] = [(part, hidden, scoped) for part in _evaluated_outside(node)]
            body = node.body if isinstance(node.body, list) else [node.body]
            return outer + [(part, hidden | own, scoped | own) for part in body]
        if isinstance(node, ast.NamedExpr):
            return [(node.value, hidden, scoped)]
        if isinstance(node, ast.AnnAssign):
            parts = [node.target] + ([node.value] if node.value is not None else [])
            return [(part, hidden, scoped) for part in parts]
        return [(part, hidden, scoped) for part in ast.iter_child_nodes(node)]

    def _names_of(self, scope: _Scope) -> frozenset[str]:
        """The names a scope inside the function hides from it: its parameters, the names its own
        code binds and those it declares global, less those it declares nonlocal."""
        kept = self._own.get(id(scope))
        if kept is None:
            body = scope.body if isinstance(scope.body, list) else [scope.body]
            bound = {name for binds, name, _ in self.met(body) if binds}
            hidden = _parameters(scope) | bound | _declared(body, ast.Global)
            kept = self._own[id(scope)] = frozenset(hidden - _declared(body, ast.Nonlocal))
        return kept


def _named(node: ast.AST, hidden: frozenset[str], scoped: frozenset[str]) -> Iterator[_Met]:
    """The names one node binds or reads itself, where the scopes around it do not hide them."""
    met: list[tuple[bool, str]] = []
    if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load | ast.Store):
        met.append((isinstance(node.ctx, ast.Store), node.id))
    elif isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
        met.append((False, node.target.id))
    elif isinstance(node, ast.NamedExpr) and node.target.id not in scoped:
        # a `:=` binds in the scope around any comprehension it is in
        yield True, node.target.id, node
    elif isinstance(node, ast.Import | ast.ImportFrom):
        met += [(True, _imported(alias)) for alias in node.names if alias.name != "*"]
    else:
        name = _bound_name(node)
        if name is not None:
            met.append((True, name))
    for bound, name in met:
        if name not in hidden:
            yield bound, name, node


def _bound_name(node: ast.AST) -> str | None:
    """The name a definition, an ``except`` or a ``match`` pattern binds, or None."""
    if isinstance(node, (*_FUNCTIONS, ast.ClassDef)):
        return node.name
    if isinstance(node, ast.ExceptHandler | ast.MatchAs | ast.MatchStar):
        return node.name
    if isinstance(node, ast.MatchMapping):
        return node.rest
    return None


def _imported(alias: ast.alias) -> str:
    """The name an import binds: its alias, or the first part of the module it names."""
    return alias.asname or alias.name.partition(".")[0]


def _comprehension_parts(
    node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp,
    hidden: frozenset[str],
    scoped: frozenset[str],
) -> list[_Pending]:
    """A comprehension's parts: its first iterable in the scope around it, and the rest where its
    own variables hide the function's."""
    first, *rest = node.generators
    own = frozenset(name for each in node.generators for name in names_in(each.target))
    parts: list[ast.AST] = [*first.ifs]
    for generator in rest:
        parts += [generator.iter, *generator.ifs]
    if isinstance(node, ast.DictComp):
        parts += [node.key, node.value]
    else:
        parts.append(node.elt)
    return [(first.iter, hidden, scoped)] + [(part, hidden | own, scoped) for part in parts]


def _evaluated_outside(scope: _Scope) -> list[ast.expr]:
    """The parts of a definition the scope around it runs: decorators, defaults, bases and
    keywords."""
    if isinstance(scope, ast.ClassDef):
        keywords = [keyword.value for keyword in scope.keywords]
        return [*scope.decorator_list, *scope.bases, *keywords]
    defaults = [*scope.args.defaults, *(each for each in scope.args.kw_defaults if each)]
    decorators = [] if isinstance(scope, ast.Lambda) else scope.decorator_list
    return [*decorators, *defaults]


def _parameters(scope: _Scope) -> set[str]:
    """A function's or lambda's parameter names; a class has none."""
    if isinstance(scope, ast.ClassDef):
        return set()
    arguments = scope.args
    every = [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs]
    every += [each for each in (arguments.vararg, arguments.kwarg) if each is not None]
    return {each.arg for each in every}


def _declared(
    body: list[ast.stmt] | list[ast.expr], kind: type[ast.Global | ast.Nonlocal]
) -> set[str]:
    """The names a scope's own code declares global, or nonlocal."""
    names: set[str] = set()
    pending: list[ast.AST] = list(body)
    while pending:
        node = pending.pop()
        if isinstance(node, kind):
            names.update(node.names)
        elif not isinstance(node, _SCOPES):
            pending.extend(ast.iter_child_nodes(node))
    return names
