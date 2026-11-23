"""Which bindings of a name can hold its value where a function reads it, worked out without
running the function (name-only-loops-that-run-before-a-condition).

The walk goes forward over the function's own statements in the order they
run, keeping for each name the bindings that can still hold its value: a
binding replaces the name's others, the two sides of a branch join, a loop
is walked again until what it holds stops growing, and a ``return``,
``raise``, ``break`` or ``continue`` ends the path it is on. At each name
the function reads, and at each augmented assignment's target, it notes the
bindings that reach that place. What a node binds, and how, is the caller's
``bind``.
"""

from __future__ import annotations

import ast
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

# what one statement or expression binds, given the innermost loop the walk is in
type Bind[T] = Callable[[ast.AST, ast.AST | None], Iterable[tuple[str, T]]]
# each name's bindings that can hold its value at one place; None where no path reaches
type State[T] = dict[str, frozenset[T]]

_DEFINITIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
_COMPREHENSIONS = (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)


def reaching[T](
    function: ast.AST, bind: Bind[T], step: Callable[[], None]
) -> dict[int, frozenset[T]]:
    """The bindings that reach each name a function reads and each augmented assignment's
    target, by the node's id. ``step`` takes one step of the analysis's pace."""
    walk: _Walk[T] = _Walk(bind, step)
    if isinstance(function, ast.Lambda):
        walk.expression(function.body, {})
    else:
        walk.block(function.body, {})  # pyrefly: ignore[missing-attribute]
    return walk.reads


@dataclass
class _Walk[T]:
    """One forward walk: what it noted, the loop it is in, the states each ``break`` and
    ``continue`` left in the loops it is in, and the bindings each ``try`` it is in has made."""

    bind: Bind[T]
    step: Callable[[], None]
    reads: dict[int, frozenset[T]] = field(default_factory=dict)
    loop: ast.AST | None = None
    jumps: list[tuple[list[State[T]], list[State[T]]]] = field(default_factory=list)
    tries: list[dict[str, set[T]]] = field(default_factory=list)

    def block(self, body: list[ast.stmt], state: State[T] | None) -> State[T] | None:
        """Walk statements in order from ``state``, changing it; what holds after them."""
        for statement in body:
            if state is None:
                return None
            self.step()
            state = _STATEMENTS.get(type(statement), _Walk._simple)(self, statement, state)
        return state

    def expression(self, node: ast.AST, state: State[T]) -> None:
        """Note each name an expression reads, and bind each walrus, in the order they run. A
        walrus in a part that can be skipped adds its binding to the name's others."""
        pending: list[tuple[ast.AST, bool, bool]] = [(node, False, False)]
        while pending:
            self.step()
            each, evaluated, maybe = pending.pop()
            if evaluated:
                self._bound(each, state, maybe)
                continue
            if isinstance(each, ast.Lambda):
                continue
            if isinstance(each, ast.Name) and isinstance(each.ctx, ast.Load):
                self._note(each, state)
            if isinstance(each, ast.NamedExpr):
                pending.append((each, True, maybe))
            parts = reversed(_in_order(each))
            pending.extend((part, False, maybe or skipped) for part, skipped in parts)

    def _note(self, name: ast.Name, state: State[T]) -> None:
        held = state.get(name.id, frozenset())
        before = self.reads.get(id(name))
        self.reads[id(name)] = held if before is None else before | held

    def _bound(self, node: ast.AST, state: State[T], maybe: bool = False) -> None:
        for name, binding in self.bind(node, self.loop):
            kept = state.get(name, frozenset()) if maybe else frozenset()
            state[name] = kept | {binding}
            for made in self.tries:
                made.setdefault(name, set()).add(binding)

    def _simple(self, node: ast.stmt, state: State[T]) -> State[T] | None:
        """A statement with no statements inside: its value, its other parts, then what it
        binds."""
        value = getattr(node, "value", None)
        parts = [part for part in ast.iter_child_nodes(node) if part is not value]
        for part in [value, *parts] if isinstance(value, ast.AST) else parts:
            self.expression(part, state)
        if isinstance(node, ast.AugAssign) and isinstance(node.target, ast.Name):
            self._note(node.target, state)
        self._bound(node, state)
        return None if isinstance(node, ast.Return | ast.Raise) else state

    def _if(self, node: ast.If, state: State[T]) -> State[T] | None:
        self.expression(node.test, state)
        return _join(self.block(node.body, dict(state)), self.block(node.orelse, state))

    def _loop(self, node: ast.For | ast.AsyncFor | ast.While, state: State[T]) -> State[T] | None:
        """A loop's passes, walked again until the state at their start stops growing, then
        its ``else``, which runs when the loop ends without a ``break``."""
        if not isinstance(node, ast.While):
            self.expression(node.iter, state)
        head, outer = state, self.loop
        while True:
            self.jumps.append(([], []))
            self.loop = node
            entry = dict(head)
            leaving = self._pass_start(node, entry)
            end = self.block(node.body, entry)
            self.loop = outer
            breaks, continues = self.jumps.pop()
            grown = _joined(head, end, *continues)
            if grown == head:
                return _join(self.block(node.orelse, leaving), *breaks)
            head = grown

    def _pass_start(
        self, node: ast.For | ast.AsyncFor | ast.While, entry: State[T]
    ) -> State[T] | None:
        """Start a pass from ``entry``: a ``while``'s test, or a ``for``'s next item. What
        holds when the loop ends there instead, None for a ``while`` whose test is always true."""
        if isinstance(node, ast.While):
            self.expression(node.test, entry)
            forever = isinstance(node.test, ast.Constant) and bool(node.test.value)
            return None if forever else dict(entry)
        leaving = dict(entry)
        self.expression(node.target, entry)
        self._bound(node, entry)
        return leaving

    def _jump(self, node: ast.Break | ast.Continue, state: State[T]) -> None:
        breaks, continues = self.jumps[-1]
        (breaks if isinstance(node, ast.Break) else continues).append(state)

    def _with(self, node: ast.With | ast.AsyncWith, state: State[T]) -> State[T] | None:
        """A ``with``: its items in order, then its body, which a manager that swallows a raise
        can leave at any point."""
        for item in node.items:
            self.expression(item.context_expr, state)
            if item.optional_vars is not None:
                self.expression(item.optional_vars, state)
            self._bound(item, state)
        return _join(*self._raising(node.body, state))

    def _try(self, node: ast.Try | ast.TryStar, state: State[T]) -> State[T] | None:
        """A ``try``: each handler, and a ``finally`` on the way out of a raise no handler
        caught, starts from any binding its body could have made, joined with its start. Only
        the paths that end normally run on past the ``finally``."""
        end, raised = self._raising(node.body, state)
        ends = [self.block(node.orelse, end)]
        for handler in node.handlers:
            start = dict(raised)
            if handler.type is not None:
                self.expression(handler.type, start)
            self._bound(handler, start)
            ends.append(self.block(handler.body, start))
        after = _join(*ends)
        if not node.finalbody:
            return after
        self.block(node.finalbody, dict(raised))
        return None if after is None else self.block(node.finalbody, after)

    def _raising(self, body: list[ast.stmt], state: State[T]) -> tuple[State[T] | None, State[T]]:
        """Walk a body that a raise can leave at any point: what holds at its end, and each
        binding that held anywhere in it."""
        made = {name: set(held) for name, held in state.items()}
        self.tries.append(made)
        end = self.block(body, state)
        self.tries.pop()
        return end, {name: frozenset(held) for name, held in made.items()}

    def _match(self, node: ast.Match, state: State[T]) -> State[T] | None:
        """A ``match``: each case from the subject's state, its captures bound before its guard,
        and the path where no case matched, unless the last case matches anything."""
        self.expression(node.subject, state)
        ends: list[State[T] | None] = [] if _matches_anything(node.cases[-1]) else [state]
        for case in node.cases:
            start = dict(state)
            self.expression(case.pattern, start)
            for part in ast.walk(case.pattern):
                self._bound(part, start)
            if case.guard is not None:
                self.expression(case.guard, start)
            ends.append(self.block(case.body, start))
        return _join(*ends)

    def _definition(self, node: ast.AST, state: State[T]) -> State[T]:
        """A ``def`` or ``class`` inside the function: the parts it evaluates where it is
        defined. Its body is another scope."""
        parts: list[ast.expr | None] = list(node.decorator_list)  # pyrefly: ignore[missing-attribute]
        if isinstance(node, ast.ClassDef):
            parts += [*node.bases, *(keyword.value for keyword in node.keywords)]
        else:
            arguments = node.args  # pyrefly: ignore[missing-attribute]
            parts += [*arguments.defaults, *arguments.kw_defaults]
        for part in parts:
            if part is not None:
                self.expression(part, state)
        self._bound(node, state)
        return state


def _matches_anything(case: ast.match_case) -> bool:
    """Whether a case matches every subject: ``case _:`` or a bare capture, with no guard."""
    pattern = case.pattern
    return case.guard is None and isinstance(pattern, ast.MatchAs) and pattern.pattern is None


def _in_order(node: ast.AST) -> list[tuple[ast.AST, bool]]:
    """A node's parts in the order they run, each with whether it can be skipped: what a
    comprehension makes and tests, and the parts of an `and`, an `or` or a conditional
    expression after the first."""
    if isinstance(node, _COMPREHENSIONS):
        first, *others = node.generators
        made = [node.key, node.value] if isinstance(node, ast.DictComp) else [node.elt]
        skipped = [first.target, *first.ifs, *others, *made]
        return [(first.iter, False), *((part, True) for part in skipped)]
    if isinstance(node, ast.BoolOp | ast.IfExp):
        first, *others = (
            [node.test, node.body, node.orelse] if isinstance(node, ast.IfExp) else node.values
        )
        return [(first, False), *((part, True) for part in others)]
    return [(part, False) for part in ast.iter_child_nodes(node)]


def _join[T](*states: State[T] | None) -> State[T] | None:
    """What holds where paths meet, None when no path reaches."""
    live = [state for state in states if state is not None]
    return _joined(live[0], *live[1:]) if live else None


def _joined[T](first: State[T], *others: State[T] | None) -> State[T]:
    """Each name's bindings from any of the paths that reach."""
    joined = dict(first)
    for other in others:
        for name, held in (other or {}).items():
            joined[name] = joined.get(name, frozenset()) | held
    return joined


_STATEMENTS: dict[type[ast.AST], Callable[..., State | None]] = {
    ast.If: _Walk._if,
    ast.For: _Walk._loop,
    ast.AsyncFor: _Walk._loop,
    ast.While: _Walk._loop,
    ast.Break: _Walk._jump,
    ast.Continue: _Walk._jump,
    ast.With: _Walk._with,
    ast.AsyncWith: _Walk._with,
    ast.Try: _Walk._try,
    ast.TryStar: _Walk._try,
    ast.Match: _Walk._match,
    **{each: _Walk._definition for each in _DEFINITIONS},
}
