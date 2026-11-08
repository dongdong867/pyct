"""Where the value a condition with no fork reads came from: a loop that changed it, or a call
that took it tracked and gave it back plain (run-missed-line-source-loop).

The condition's function is read backward, without running it: the names
the condition reads, the statements of the function that bind those names,
the names those statements read, and so on. A path ends at a parameter, at a
name bound inside a loop, a ``for`` or ``while`` of the function or a
comprehension, which is a loop source, and at a call where an input
recorded a downgrade of that call's name, which is a lost source. A name
the function never binds, a global or another function's local, ends a
path with no source, and so does an attribute's value, which is read
through the name it hangs off.
"""

from __future__ import annotations

import ast
import types
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field

from pyct.core.foundation.branch import Site
from pyct.results.causes import Source, SourceKind

# a place in the code, as a downgrade's site and an AST node's start give it
type At = tuple[int, int]

_FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
_SCOPES = (*_FUNCTIONS, ast.ClassDef)
_LOOPS = (ast.For, ast.AsyncFor, ast.While)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
# the parts a downgrade's site can name
_LOSES = (ast.Call, ast.BinOp, ast.UnaryOp, ast.Compare, ast.Subscript)


@dataclass(frozen=True)
class _Binding:
    """One place the function binds a name: the expression it reads, if any, and the innermost
    loop around it, or the loop itself for a ``for`` target."""

    value: ast.expr | None
    loop: ast.stmt | None


@dataclass
class Origins:
    """The sources of one file's conditions, its source read once when first asked.

    ``lost`` holds the names of the downgrades the run's inputs recorded in
    the file, by site. ``step`` takes one step of the analysis's pace, and
    raises when its stop has come.
    """

    file: str
    lost: Mapping[At, tuple[str, ...]]
    step: Callable[[], None]
    _read: bool = False
    _functions: dict[tuple[int, str], ast.AST] = field(default_factory=dict)

    def of(self, code: types.CodeType, line: int, col: int) -> tuple[Source, ...]:
        """The sources of the condition at ``line`` and ``col`` in ``code``, in code order."""
        function = self._function(code)
        if function is None:
            return ()
        test = _test_at(function, line, col)
        if test is None:
            return ()
        return _Reading(self, _bindings(function, self.step)).sources(test)

    def _function(self, code: types.CodeType) -> ast.AST | None:
        if not self._read:
            self._read = True
            tree = _parsed(self.file)
            if tree is not None:
                for node in ast.walk(tree):
                    self.step()
                    if isinstance(node, _FUNCTIONS):
                        self._functions.setdefault((_first_line(node), _name(node)), node)
        return self._functions.get((code.co_firstlineno, code.co_name))


def _parsed(file: str) -> ast.Module | None:
    """The module as it reads now, or None when it no longer reads."""
    try:
        with open(file, encoding="utf-8") as source:
            return ast.parse(source.read(), file)
    except (OSError, SyntaxError, ValueError):
        return None


def _first_line(node: ast.AST) -> int:
    """The line a function's code starts on: its first decorator's, else its own."""
    decorators = getattr(node, "decorator_list", [])
    return decorators[0].lineno if decorators else node.lineno  # pyrefly: ignore[missing-attribute]


def _name(node: ast.AST) -> str:
    return "<lambda>" if isinstance(node, ast.Lambda) else node.name  # pyrefly: ignore[missing-attribute]


def _test_at(function: ast.AST, line: int, col: int) -> ast.expr | None:
    """The expression a condition at ``line`` and ``col`` tests: the innermost test written there,
    else the outermost expression that starts there."""
    tests = [node for node in _tests(function) if (node.lineno, node.col_offset) == (line, col)]
    if tests:
        return tests[-1]
    starting = [
        node
        for node in _own_nodes(function)
        if isinstance(node, ast.expr) and (node.lineno, node.col_offset) == (line, col)
    ]
    return starting[0] if starting else None


def _tests(function: ast.AST) -> Iterator[ast.expr]:
    """Each expression the function tests for truth, outer before inner."""
    for node in _own_nodes(function):
        if isinstance(node, ast.If | ast.While | ast.IfExp | ast.Assert):
            yield from _parts_of(node.test)
        elif isinstance(node, ast.comprehension):
            for test in node.ifs:
                yield from _parts_of(test)


def _parts_of(test: ast.expr) -> Iterator[ast.expr]:
    """A test, then each operand of the `and`, `or` and `not` it is made of."""
    yield test
    if isinstance(test, ast.BoolOp):
        for value in test.values:
            yield from _parts_of(value)
    elif isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        yield from _parts_of(test.operand)


def _own_nodes(scope: ast.AST) -> Iterator[ast.AST]:
    """The nodes of a function's own body, in code order, without those of a function or class
    defined inside it."""
    body = scope.body if not isinstance(scope, ast.Lambda) else [scope.body]  # pyrefly: ignore[missing-attribute]
    pending: list[ast.AST] = list(reversed(body))
    while pending:
        node = pending.pop()
        yield node
        if isinstance(node, _SCOPES):
            continue
        pending.extend(reversed(list(ast.iter_child_nodes(node))))


def _bindings(function: ast.AST, step: Callable[[], None]) -> dict[str, list[_Binding]]:
    """Each name the function binds, with every place it binds it; a parameter has none."""
    bound: dict[str, list[_Binding]] = {}
    for node, loop in _with_loops(function, step):
        for name, binding in _bound_by(node, loop):
            bound.setdefault(name, []).append(binding)
    return bound


def _with_loops(
    scope: ast.AST, step: Callable[[], None]
) -> Iterator[tuple[ast.AST, ast.stmt | None]]:
    """Each statement and expression of the function's own body, with the innermost loop
    around it: a loop's body and its test are inside it, a ``for``'s iterable and a loop's
    ``else`` are not."""
    body = scope.body if not isinstance(scope, ast.Lambda) else [scope.body]  # pyrefly: ignore[missing-attribute]
    pending: list[tuple[ast.AST, ast.stmt | None]] = [(node, None) for node in reversed(body)]
    while pending:
        step()
        node, loop = pending.pop()
        yield node, loop
        if isinstance(node, _SCOPES):
            continue
        outside = _outside(node) if isinstance(node, _LOOPS) else []
        children = [
            (child, node if isinstance(node, _LOOPS) and child not in outside else loop)
            for child in ast.iter_child_nodes(node)
        ]
        pending.extend(reversed(children))


def _outside(loop: ast.For | ast.AsyncFor | ast.While) -> list[ast.AST]:
    """The parts of a loop that run once, not on each pass."""
    once: list[ast.AST] = list(loop.orelse)
    if isinstance(loop, ast.For | ast.AsyncFor):
        once.append(loop.iter)
    return once


def _bound_by(node: ast.AST, loop: ast.stmt | None) -> Iterator[tuple[str, _Binding]]:
    """The names one statement or expression binds, each with how."""
    if isinstance(node, ast.Assign):
        for target in node.targets:
            for name in _names_in(target):
                yield name, _Binding(node.value, loop)
    elif isinstance(node, ast.AugAssign | ast.AnnAssign | ast.NamedExpr) and node.value is not None:
        # an augmented assignment reads its own name too, which the reading has already read
        for name in _names_in(node.target):
            yield name, _Binding(node.value, loop)
    elif isinstance(node, ast.For | ast.AsyncFor):
        for name in _names_in(node.target):
            yield name, _Binding(node.iter, node)
    elif isinstance(node, ast.withitem) and node.optional_vars is not None:
        for name in _names_in(node.optional_vars):
            yield name, _Binding(node.context_expr, loop)


def _names_in(target: ast.expr) -> Iterator[str]:
    """The plain names an assignment target binds; an attribute or a subscript binds none."""
    if isinstance(target, ast.Name):
        yield target.id
    elif isinstance(target, ast.Tuple | ast.List):
        for element in target.elts:
            yield from _names_in(element)
    elif isinstance(target, ast.Starred):
        yield from _names_in(target.value)


@dataclass
class _Reading:
    """One backward reading from a condition: the names already read, and the sources found."""

    origins: Origins
    bound: dict[str, list[_Binding]]
    seen: set[str] = field(default_factory=set)
    found: dict[tuple[SourceKind, str, At], Source] = field(default_factory=dict)

    def sources(self, test: ast.expr) -> tuple[Source, ...]:
        pending = list(self._read(test, None))
        while pending:
            self.origins.step()
            name = pending.pop()
            if name in self.seen:
                continue
            self.seen.add(name)
            for binding in self.bound.get(name, []):
                pending.extend(self._followed(name, binding))
        return tuple(
            sorted(self.found.values(), key=lambda source: (source.site.line, source.site.col))
        )

    def _followed(self, name: str, binding: _Binding) -> Iterator[str]:
        """The names to read next from one binding of ``name``, after any source it is."""
        if binding.loop is not None:
            self._add(SourceKind.LOOP, name, binding.loop)
            return
        if binding.value is not None:
            yield from self._read(binding.value, name)

    def _read(self, expression: ast.expr, name: str | None) -> Iterator[str]:
        """The names an expression reads outside a call that lost a value and outside a
        comprehension, after each of those is noted as a source."""
        pending: list[ast.AST] = [expression]
        while pending:
            self.origins.step()
            node = pending.pop()
            if isinstance(node, _COMPREHENSIONS):
                self._add(SourceKind.LOOP, name or _first_name(node), node)
                continue
            if self._lost_in(node):
                continue
            if isinstance(node, ast.Lambda):
                continue
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                yield node.id
            pending.extend(reversed(list(ast.iter_child_nodes(node))))

    def _lost_in(self, node: ast.AST) -> bool:
        """Whether an input recorded a downgrade of this part at its site, noted as a lost
        source of the first name the part reads: a call's by the name the call writes, or by
        the last name after its dot, and a call's, an operator's or a subscript's by a dunder."""
        if not isinstance(node, _LOSES):
            return False
        names = self.origins.lost.get((node.lineno, node.col_offset), ())
        written = _written(node)
        called = next((name for name in names if name in written or _dunder(name)), None)
        if called is None:
            return False
        self._add(SourceKind.LOST, _first_name(node), node, called)
        return True

    def _add(self, kind: SourceKind, name: str, node: ast.AST, call: str | None = None) -> None:
        site = Site(file=self.origins.file, line=node.lineno, col=node.col_offset)  # pyrefly: ignore[missing-attribute]
        self.found.setdefault((kind, name, (site.line, site.col)), Source(kind, name, site, call))


def _written(node: ast.AST) -> frozenset[str]:
    """The names a call is written with: its callee's text, and the last name after its dot."""
    if not isinstance(node, ast.Call):
        return frozenset()
    last = [node.func.attr] if isinstance(node.func, ast.Attribute) else []
    return frozenset([ast.unparse(node.func), *last])


def _dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _first_name(node: ast.AST) -> str:
    """The first name an expression reads as a value, else its text: a comprehension's first
    iterable's, and within a call its arguments' before its callee's (`_in_order`)."""
    part = node.generators[0].iter if isinstance(node, _COMPREHENSIONS) else node
    for each in _in_order(part):
        if isinstance(each, ast.Name) and isinstance(each.ctx, ast.Load):
            return each.id
    return ast.unparse(node)


def _in_order(node: ast.AST) -> Iterator[ast.AST]:
    """The node and the nodes under it, each before its children, in the order written but for
    a call's, whose arguments come before its callee: the callee is what reads them."""
    pending = [node]
    while pending:
        each = pending.pop()
        yield each
        if isinstance(each, ast.Call):
            children = [*each.args, *each.keywords, each.func]
        else:
            children = list(ast.iter_child_nodes(each))
        pending.extend(reversed(children))
