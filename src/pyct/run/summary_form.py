"""Summaries' form check of the reply's code, which reads the parsed code before anything runs.

A formula is one function, ``summary``, on the loop's parameters, of at most
``MOST_STATEMENTS`` statements, each an assignment to names or an ``if``
holding the same, and a last ``return`` of a dict display keyed by the
changed names; a leading docstring and a ``pass`` do nothing, and the check
drops or skips them (``formula_body``). The definition holds its name, its parameters, each a bare
name, and its body alone, since the child evaluates the rest of a ``def``
line as it runs the module. The check reads each field of the module, the
definition, its parameters and each statement, and refuses a node with a
field it does not read. Each expression keeps to a rewrite's rules
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
# the fields of each node of the module and its statements that the check reads; a node with a
# field not named here, as a later Python may add, is refused until the check reads it
_READ: dict[type[ast.AST], frozenset[str]] = {
    ast.Module: frozenset({"body", "type_ignores"}),
    ast.FunctionDef: frozenset(
        {"name", "args", "body", "decorator_list", "returns", "type_comment", "type_params"}
    ),
    ast.arguments: frozenset(
        {"posonlyargs", "args", "vararg", "kwonlyargs", "kw_defaults", "kwarg", "defaults"}
    ),
    ast.arg: frozenset({"arg", "annotation", "type_comment"}),
    ast.Assign: frozenset({"targets", "value", "type_comment"}),
    ast.AugAssign: frozenset({"target", "op", "value"}),
    ast.If: frozenset({"test", "body", "orelse"}),
    ast.Return: frozenset({"value"}),
    ast.Name: frozenset({"id", "ctx"}),
    ast.Dict: frozenset({"keys", "values"}),
}
_TYPE_COMMENT = "a formula may not hold a type comment"
_STATEMENTS_REFUSED: dict[type[ast.AST], str] = {
    ast.For: "a loop",
    ast.AsyncFor: "a loop",
    ast.While: "a loop",
    ast.Import: "an import",
    ast.ImportFrom: "an import",
    ast.Expr: "an expression statement",
    ast.Delete: "a del statement",
    ast.TypeAlias: "a type statement",
    ast.With: "a with statement",
    ast.AsyncWith: "a with statement",
    ast.Match: "a match statement",
    ast.Raise: "a raise statement",
    ast.Try: "a try statement",
    ast.TryStar: "a try statement",
    ast.Assert: "an assert statement",
    ast.Global: "a global statement",
    ast.Nonlocal: "a nonlocal statement",
    ast.Break: "a break statement",
    ast.Continue: "a continue statement",
}


class FormCheck:
    """Summaries' form check, which ``compile_model_code`` calls on the parsed module: the tree
    with pyct's two functions after the formula, or why it is refused."""

    def __init__(self, parameters: tuple[str, ...], changed: tuple[str, ...]) -> None:
        self.parameters = parameters
        self.changed = changed

    def __call__(self, tree: ast.Module) -> ast.Module | str:
        refused = _one_function(tree)
        if refused is not None:
            return refused
        function = tree.body[0]
        assert isinstance(function, ast.FunctionDef)
        function.body = formula_body(function)
        refused = _def_line(function, self.parameters) or self._body(function.body)
        if refused is not None:
            return refused
        tree.body.extend(ast.parse(_DRIVERS).body)
        return tree

    def _body(self, body: list[ast.stmt]) -> str | None:
        """Why the function's body is outside the form, or None."""
        statements = [each for each in _walked(body) if not isinstance(each, ast.Pass)]
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
        assert isinstance(value, ast.Dict)
        return _unread(value)


def formula_body(function: ast.FunctionDef) -> list[ast.stmt]:
    """The function's body less what does nothing: a leading docstring and each pass statement
    at its top level; the body as written when nothing else is left in it. A pass inside an if
    statement stays, and the check accepts it and does not count it."""
    body = function.body
    first = body[0].value if isinstance(body[0], ast.Expr) else None
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        body = body[1:]
    return [each for each in body if not isinstance(each, ast.Pass)] or function.body


def _one_function(tree: ast.Module) -> str | None:
    """Why the module is not one function definition alone, or None."""
    body = tree.body
    for statement in body:
        if isinstance(statement, ast.Import | ast.ImportFrom):
            return "a formula may not import"
    names = [each.name for each in body if isinstance(each, ast.FunctionDef)]
    if len(names) != len(body) or not names:
        return f"the code must define one function, {SUMMARY}, and nothing else"
    other = next((name for name in names if name != SUMMARY), None)
    if other is not None:
        return f"a formula may not define {other}"
    if len(names) > 1:
        return f"the code must define {SUMMARY} once"
    return _unread(tree) or (_TYPE_COMMENT if tree.type_ignores else None)


def _def_line(function: ast.FunctionDef, parameters: tuple[str, ...]) -> str | None:
    """Why the definition holds more than its name, the formula's parameters, each bare, and its
    body, or None: a field the check does not read; else every cause in one reason, parameters
    that are not exactly the formula's first, then what the line holds that a formula may not."""
    every = _every_parameter(function.args)
    refused = next(filter(None, map(_unread, [function, function.args, *every])), None)
    if refused is not None:
        return refused
    causes = []
    if not _exact(function.args, parameters):
        listed = ", ".join(parameters) or "none"
        causes.append(f"{SUMMARY} must take exactly the parameters {listed}")
    held = _held(function, every)
    if held:
        either = f"{', '.join(held[:-1])} or {held[-1]}" if len(held) > 1 else held[0]
        causes.append(f"a formula may not {either}")
    return "; ".join(causes) or None


def _every_parameter(arguments: ast.arguments) -> list[ast.arg]:
    """Each parameter the definition names, the starred ones included."""
    stars = [each for each in (arguments.vararg, arguments.kwarg) if each is not None]
    return [*arguments.posonlyargs, *arguments.args, *arguments.kwonlyargs, *stars]


def _exact(arguments: ast.arguments, parameters: tuple[str, ...]) -> bool:
    """Whether the definition takes exactly the formula's parameters, each once, by position or
    name, with no default."""
    names = [each.arg for each in arguments.args]
    others = (arguments.posonlyargs, arguments.kwonlyargs, arguments.kw_defaults)
    stars = (arguments.vararg, arguments.kwarg)
    plain = not any((*others, arguments.defaults, *stars))
    return plain and sorted(names) == sorted(parameters) and len(set(names)) == len(names)


def _held(function: ast.FunctionDef, every: list[ast.arg]) -> list[str]:
    """What the definition holds that a formula may not, each as what it may not do, in the
    order the line writes them: a decorator, type parameters, annotations, a type comment."""
    annotated = [
        what
        for what, held in (
            ("its parameters", any(each.annotation is not None for each in every)),
            ("its return", function.returns is not None),
        )
        if held
    ]
    held = ["use a decorator"] if function.decorator_list else []
    if function.type_params:
        held.append("take type parameters")
    if annotated:
        held.append(f"annotate {' or '.join(annotated)}")
    if function.type_comment is not None or any(each.type_comment for each in every):
        held.append("hold a type comment")
    return held


def _unread(node: ast.AST) -> str | None:
    """Why the node holds a field the check does not read, or None."""
    kind = next(each for each in type(node).__mro__ if each in _READ)
    unread = [name for name in node._fields if name not in _READ[kind]]
    if not unread:
        return None
    return f"a formula may not use the field {kind.__name__}.{unread[0]}, which pyct does not read"


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
    """Why one statement is outside the form, or None: an assignment to names alone, an if, a
    pass, or the last statement's return, each holding no type comment."""
    if isinstance(statement, ast.Pass):
        return None
    if not isinstance(statement, ast.Return | ast.If | ast.Assign | ast.AugAssign):
        return _kind_refusal(statement)
    if isinstance(statement, ast.Return) and statement is not last:
        return "a formula returns only as its last statement"
    targets = _targets(statement)
    if not all(isinstance(each, ast.Name) for each in targets):
        return "a formula assigns only to names"
    if isinstance(statement, ast.Assign) and statement.type_comment is not None:
        return _TYPE_COMMENT
    return next(filter(None, map(_unread, [statement, *targets])), None)


def _kind_refusal(statement: ast.stmt) -> str:
    """Why a statement of a kind outside the form is refused."""
    if isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
        return f"a formula may not define {statement.name}"
    if isinstance(statement, ast.AnnAssign):
        return "a formula may not annotate a name"
    named = type(statement).__name__
    kind = _STATEMENTS_REFUSED.get(type(statement), f"the statement {named}")
    return f"a formula may not use {kind}"


def _targets(statement: ast.stmt) -> list[ast.expr]:
    """What an assignment binds, as written; nothing for another statement."""
    if isinstance(statement, ast.Assign):
        return statement.targets
    if isinstance(statement, ast.AugAssign):
        return [statement.target]
    return []


def _assigned(statement: ast.stmt) -> list[str]:
    """The names an assignment binds."""
    return [each.id for each in _targets(statement) if isinstance(each, ast.Name)]


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
