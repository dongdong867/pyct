"""Summaries' form check of the reply's code, which reads the parsed code before anything runs.

A formula is one function, ``summary``, on the loop's parameters, of at most
``MOST_STATEMENTS`` statements, each an assignment to names or an ``if``
holding the same, and a last ``return`` of a dict display keyed by the
changed names. Each expression keeps to a rewrite's rules
(``pyct.rewrite.condition.refusal``), reading the parameters and the names
the function assigns, and calling ``FORMULA_CALLS`` by name. pyct then
writes two functions of its own after it, ``PAST`` and ``FOLLOW``, which run
it in the child and call back into pyct's plain Python through ``RUNS`` and
``TRACKED``.
"""

from __future__ import annotations

import ast

from pyct.rewrite.condition import CALLS, LITERALS, ExpressionRules, refusal

# the functions a formula may call by name: a rewrite's, and those that gather a list's values
FORMULA_CALLS = CALLS | frozenset({"sum", "round", "sorted", "divmod"})
# the literals a formula may write: a rewrite's, and bytes
FORMULA_LITERALS = (*LITERALS, bytes)
# the statements a formula holds at most, the ones inside its if statements counted
MOST_STATEMENTS = 10
# the function a formula is written as
SUMMARY = "summary"

# pyct's two functions after the formula: each calls back into pyct with the formula
PAST, FOLLOW = "__pyct_past__", "__pyct_follow__"
RUNS, TRACKED = "__pyct_runs__", "__pyct_tracked__"
_DRIVERS = f"""
def {PAST}():
    return {RUNS}({SUMMARY})


def {FOLLOW}(**leaves):
    return {TRACKED}({SUMMARY}, leaves)
"""
_STATEMENTS_REFUSED: dict[type[ast.AST], str] = {
    ast.For: "a loop",
    ast.AsyncFor: "a loop",
    ast.While: "a loop",
    ast.Import: "an import",
    ast.ImportFrom: "an import",
}


class FormCheck:
    """Summaries' form check, which ``compile_model_code`` calls on the parsed module: the tree
    with pyct's two functions after the formula, or why it is refused."""

    def __init__(self, parameters: tuple[str, ...], changed: tuple[str, ...]) -> None:
        self.parameters = parameters
        self.changed = changed

    def __call__(self, tree: ast.Module) -> ast.Module | str:
        refused = _one_function(tree.body)
        if refused is not None:
            return refused
        function = tree.body[0]
        assert isinstance(function, ast.FunctionDef)
        refused = self._signature(function) or self._body(function.body)
        if refused is not None:
            return refused
        tree.body.extend(ast.parse(_DRIVERS).body)
        return tree

    def _signature(self, function: ast.FunctionDef) -> str | None:
        """Why the function is not ``summary`` taking exactly the parameters, or None."""
        arguments = function.args
        names = [each.arg for each in arguments.args]
        others = (arguments.posonlyargs, arguments.kwonlyargs, arguments.defaults)
        plain = not any(others) and arguments.vararg is None and arguments.kwarg is None
        if function.decorator_list:
            return "a formula may not use a decorator"
        if not plain or sorted(names) != sorted(self.parameters) or len(set(names)) < len(names):
            listed = ", ".join(self.parameters) or "none"
            return f"{SUMMARY} must take exactly the parameters {listed}"
        return None

    def _body(self, body: list[ast.stmt]) -> str | None:
        """Why the function's body is outside the form, or None."""
        statements = list(_walked(body))
        if len(statements) > MOST_STATEMENTS:
            return f"a formula may hold at most {MOST_STATEMENTS} statements"
        last = body[-1]
        for statement in statements:
            refused = _statement_refusal(statement, last)
            if refused is not None:
                return refused
        refused = self._returned(last)
        if refused is not None:
            return refused
        assigned = {name for each in statements for name in _assigned(each)}
        names = frozenset(self.parameters) | assigned
        rules = ExpressionRules("formula", names, calls=FORMULA_CALLS, literals=FORMULA_LITERALS)
        for expression in _expressions(statements):
            refused = refusal(expression, rules)
            if refused is not None:
                return refused
        return None

    def _returned(self, last: ast.stmt) -> str | None:
        """Why the last statement does not return a dict display keyed by each changed name
        once, or None."""
        value = last.value if isinstance(last, ast.Return) else None
        keys = value.keys if isinstance(value, ast.Dict) else [None]
        written = [
            each.value
            for each in keys
            if isinstance(each, ast.Constant) and isinstance(each.value, str)
        ]
        if len(written) != len(keys) or sorted(written) != sorted(self.changed):
            listed = ", ".join(f'"{name}"' for name in self.changed)
            return f"{SUMMARY} must end by returning a dict with one entry for each of {listed}"
        return None


def _one_function(body: list[ast.stmt]) -> str | None:
    """Why the module is not one function definition, or None."""
    for statement in body:
        if isinstance(statement, ast.Import | ast.ImportFrom):
            return "a formula may not import"
    names = [each.name for each in body if isinstance(each, ast.FunctionDef)]
    if len(names) != len(body) or not names:
        return f"the code must define one function, {SUMMARY}, and nothing else"
    other = next((name for name in names if name != SUMMARY), None)
    if other is not None:
        return f"a formula may not define {other}"
    return None if len(names) == 1 else f"the code must define {SUMMARY} once"


def _walked(body: list[ast.stmt]) -> list[ast.stmt]:
    """Each statement of the body, an if statement's own ones after it, in the order written."""
    found: list[ast.stmt] = []
    pending = list(reversed(body))
    while pending:
        statement = pending.pop()
        found.append(statement)
        if isinstance(statement, ast.If):
            pending.extend(reversed([*statement.body, *statement.orelse]))
    return found


def _statement_refusal(statement: ast.stmt, last: ast.stmt) -> str | None:
    """Why one statement is outside the form, or None: only the last returns."""
    if isinstance(statement, ast.Return):
        return None if statement is last else "a formula returns only as its last statement"
    if isinstance(statement, ast.If):
        return None
    if isinstance(statement, ast.Assign | ast.AugAssign):
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        named = all(isinstance(each, ast.Name) for each in targets)
        return None if named else "a formula assigns only to names"
    if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return f"a formula may not define {statement.name}"
    kind = _STATEMENTS_REFUSED.get(type(statement), f"a {type(statement).__name__} statement")
    return f"a formula may not use {kind}"


def _assigned(statement: ast.stmt) -> list[str]:
    """The names an assignment binds."""
    if isinstance(statement, ast.Assign):
        return [each.id for each in statement.targets if isinstance(each, ast.Name)]
    if isinstance(statement, ast.AugAssign) and isinstance(statement.target, ast.Name):
        return [statement.target.id]
    return []


def _expressions(statements: list[ast.stmt]) -> list[ast.expr]:
    """Each expression the statements read: an assignment's value, an augmented one's target
    too, an if's test, and the returned dict's values."""
    found: list[ast.expr] = []
    for statement in statements:
        if isinstance(statement, ast.Assign):
            found.append(statement.value)
        elif isinstance(statement, ast.AugAssign):
            found += [statement.target, statement.value]
        elif isinstance(statement, ast.If):
            found.append(statement.test)
        elif isinstance(statement, ast.Return) and isinstance(statement.value, ast.Dict):
            found += statement.value.values
    return found
