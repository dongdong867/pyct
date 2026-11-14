"""A loop's summary as the model writes it: the answer's form the request gives, the form check of
the reply's code, and the two checks the formula runs through before it is kept.

The form check reads the parsed code before anything runs: one function,
``summary``, on the loop's parameters, of at most ``MOST_STATEMENTS``
statements, each an assignment to names or an ``if`` holding the same, and a
last ``return`` of a dict display keyed by the changed names. Each
expression keeps to a rewrite's rules (``pyct.rewrite.condition.refusal``),
reading the parameters and the names the function assigns, and calling
``FORMULA_CALLS`` by name. pyct then writes two functions of its own after
it, which run it in the child and call back into pyct's plain Python.

The formula runs only in a child forked from pyct's process
(`pyct.run.model_runs`). First, in one child, on every complete run in
plain Python: each changed value it gives, as JSON text, must be the one
recorded. Then, in a second child, on the latest complete run with the
parameters that were tracked when that run started bound as leaves and the
others plain: each value it gives must come back tracked. Each child ends
within ``CHECK_SECONDS``, or at the run's deadline when that comes first.
"""

from __future__ import annotations

import ast
import json
import math
import textwrap
import time
import types
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pyct.core.entry.bases import TRACKED_CLASSES
from pyct.core.entry.plain_json import plain_json
from pyct.core.foundation.branch import PieceRun
from pyct.execution.blame import one_line
from pyct.intercept.model_code import Refused, compile_model_code
from pyct.results.failure import FailureKind
from pyct.rewrite.condition import CALLS, LITERALS, ExpressionRules, refusal
from pyct.run.model_runs import CannotFork, ModelCall, ModelRun, run_model
from pyct.run.process import InputStartError

# the functions a formula may call by name: a rewrite's, and those that gather a list's values
FORMULA_CALLS = CALLS | frozenset({"sum", "round", "sorted", "divmod"})
# the literals a formula may write: a rewrite's, and bytes
FORMULA_LITERALS = (*LITERALS, bytes)
# the statements a formula holds at most, the ones inside its if statements counted
MOST_STATEMENTS = 10
# the function a formula is written as
SUMMARY = "summary"
# the seconds each check's child may take at most
CHECK_SECONDS = 2.0
# why no check could run beside a second thread of pyct's process
CANNOT_FORK = "cannot fork"

# pyct's two functions after the formula: each calls back into pyct with the formula
_PAST, _FOLLOW = "__pyct_past__", "__pyct_follow__"
_RUNS, _TRACKED = "__pyct_runs__", "__pyct_tracked__"
_DRIVERS = f"""
def {_PAST}():
    return {_RUNS}({SUMMARY})


def {_FOLLOW}(**leaves):
    return {_TRACKED}({SUMMARY}, leaves)
"""
_STATEMENTS_REFUSED: dict[type[ast.AST], str] = {
    ast.For: "a loop",
    ast.AsyncFor: "a loop",
    ast.While: "a loop",
    ast.Import: "an import",
    ast.ImportFrom: "an import",
}


def answer_form(parameters: Sequence[str], changed: Sequence[str]) -> str:
    """How the reply writes a formula for a loop with these names going in and changed."""
    entries = ", ".join(f'"{name}": ...' for name in changed)
    calls = ", ".join(sorted(FORMULA_CALLS))
    return (
        "Answer with one fenced Python code block that defines one function and nothing else:"
        f" def {SUMMARY}({', '.join(parameters)}):, which gives the values the loop leaves in"
        " its changed names from the values going in, without a loop. It holds at most"
        f" {MOST_STATEMENTS} statements, each an assignment to a name or an if statement that"
        " holds the same, and ends with a return of a dict with one entry per changed name,"
        f" keyed by the name: return {{{entries}}}. It may read its parameters, the names it"
        ' assigns, and their items, written x[i] or d["k"]; literals; comparisons; and, or,'
        f" not; arithmetic; {calls}; math.<function>; and the methods of the values whose names"
        " do not start with _, other than format and format_map. It has no import, other"
        " function, lambda, loop, comprehension, if expression or call of itself."
    )


@dataclass(frozen=True)
class Formula:
    """A formula that passed the form check: its module code, and how stderr writes it, on one
    line, or, with ``below``, as statements on the lines below."""

    code: types.CodeType
    text: str
    below: bool


@dataclass(frozen=True)
class CompleteRun:
    """A recorded run of a loop that holds every name it changes, and the input that recorded
    it, numbered in the run from 1."""

    number: int
    run: PieceRun


@dataclass(frozen=True)
class Ended:
    """A check that could not run, and why: no child could fork or start."""

    reason: str


def formula_code(
    text: str, parameters: Sequence[str], changed: Sequence[str], file: str
) -> Formula | Refused:
    """The formula the reply's code writes, compiled with pyct's two functions after it, each
    code object named ``file``; or why it is refused."""
    code = compile_model_code(text, file, _FormCheck(tuple(parameters), tuple(changed)))
    if isinstance(code, Refused):
        return code
    function = ast.parse(text).body[0]
    assert isinstance(function, ast.FunctionDef)
    body = function.body
    if len(body) == 1:
        returned = body[0]
        assert isinstance(returned, ast.Return) and isinstance(returned.value, ast.Dict)
        entries = zip(returned.value.keys, returned.value.values, strict=True)
        written = [f"{_key(key)} = {ast.get_source_segment(text, value)}" for key, value in entries]
        return Formula(code, "; ".join(written), below=False)
    lines = text.splitlines()[body[0].lineno - 1 : body[-1].end_lineno]
    return Formula(code, textwrap.dedent("\n".join(lines)), below=True)


def _key(key: ast.expr | None) -> str:
    assert isinstance(key, ast.Constant) and isinstance(key.value, str)
    return key.value


class _FormCheck:
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


def check_formula(
    code: types.CodeType,
    runs: Sequence[CompleteRun],
    parameters: Sequence[str],
    changed: Sequence[str],
    until: float | None,
) -> str | Ended | None:
    """None when the formula gives each changed value of every run, then gives values pyct
    follows on the latest; else why the try failed, or why a check could not run."""
    failed = _past(code, runs, parameters, changed, until)
    if failed is not None:
        return failed
    return _followed(code, runs[-1], parameters, changed, until)


def _past(
    code: types.CodeType,
    runs: Sequence[CompleteRun],
    parameters: Sequence[str],
    changed: Sequence[str],
    until: float | None,
) -> str | Ended | None:
    """The formula on every run in one child, in plain Python: the first value it gives that is
    not the one recorded, or how it failed."""
    values = [_going_in(each.run, parameters) for each in runs]
    names = {"math": math, _RUNS: _runner(values, changed)}
    ran = _child(ModelCall(code, _PAST, {}, names), until)
    if not isinstance(ran, ModelRun):
        return ran
    answer = _answer(ran, "on the past runs")
    if isinstance(answer, str):
        return answer
    rows: list[dict[str, str]] = answer["rows"]
    for each, row in zip(runs, rows, strict=False):
        recorded = {value.name: value.value for value in each.run.changed}
        for name in changed:
            if row[name] != recorded[name]:
                return (
                    f"at input {each.number}, {name} was {recorded[name]},"
                    f" the formula gave {row[name]}"
                )
    if "raised" in answer:
        return f"it raised at input {runs[len(rows)].number}: {answer['raised']}"
    return None


def _followed(
    code: types.CodeType,
    latest: CompleteRun,
    parameters: Sequence[str],
    changed: Sequence[str],
    until: float | None,
) -> str | Ended | None:
    """The formula on the latest run in a second child, the parameters tracked when it started
    bound as leaves: why a value it gives is not tracked, or how it failed."""
    values = _going_in(latest.run, parameters)
    tracked = {each.name for each in latest.run.going_in if each.tracked}
    leaves = {name: value for name, value in values.items() if name in tracked}
    plain = {name: value for name, value in values.items() if name not in tracked}
    names = {"math": math, _TRACKED: _tracker(plain, changed)}
    ran = _child(ModelCall(code, _FOLLOW, leaves, names), until)
    if not isinstance(ran, ModelRun):
        return ran
    answer = _answer(ran, f"at input {latest.number}")
    if isinstance(answer, str):
        return answer
    lost = [name for name in changed if not answer[name]]
    if not lost:
        return None
    downgrades = list(dict.fromkeys(each.name for each in ran.result.downgrades))
    if downgrades:
        return f"pyct does not follow {', '.join(downgrades)}"
    return f"{lost[0]} is not tracked"


def _going_in(run: PieceRun, parameters: Sequence[str]) -> dict[str, object]:
    """The run's value of each parameter, read from its JSON text."""
    held = {each.name: each.value for each in run.going_in}
    return {name: json.loads(held[name]) for name in parameters}


def _child(call: ModelCall, until: float | None) -> ModelRun | Ended:
    """The call run in a child forked from pyct's process, within ``CHECK_SECONDS`` or by
    ``until``, whichever comes first; or why it did not run."""
    end = time.monotonic() + CHECK_SECONDS
    try:
        ran = run_model(call, end if until is None else min(end, until))
    except InputStartError as error:
        return Ended(f"cannot start a child: {error}")
    return Ended(CANNOT_FORK) if isinstance(ran, CannotFork) else ran


def _answer(ran: ModelRun, where: str) -> dict[str, Any] | str:
    """The child's answer, or why it gave none: the formula raised or did not finish
    ``where`` it ran, or gave an answer pyct could not read back."""
    failure = ran.result.failure
    if failure is not None:
        verb = "raised" if failure.kind is FailureKind.TARGET_RAISED else "did not finish"
        return f"it {verb} {where}: {failure.detail}"
    if ran.answer is None:
        return f"its answer could not be read back: {ran.unencoded}"
    answer = json.loads(ran.answer)
    assert isinstance(answer, dict)
    return answer


def _runner(
    values: list[dict[str, object]], changed: Sequence[str]
) -> Callable[[Callable[..., Any]], object]:
    """What the past-run check's child calls with the formula: each run's changed values as
    JSON text, until one raises, which it names."""

    def run(summary: Callable[..., Any]) -> object:
        rows: list[dict[str, str]] = []
        for each in values:
            try:
                got = summary(**each)
            except Exception as error:  # noqa: BLE001 - the formula's raise ends its check
                return {"rows": rows, "raised": one_line(error)}
            rows.append({name: _text(got[name]) for name in changed})
        return {"rows": rows}

    return run


def _tracker(
    plain: Mapping[str, object], changed: Sequence[str]
) -> Callable[[Callable[..., Any], Mapping[str, object]], object]:
    """What the tracked check's child calls with the formula and its leaves: whether each
    changed value it gives is tracked."""

    def tracked(summary: Callable[..., Any], leaves: Mapping[str, object]) -> object:
        got = summary(**leaves, **plain)
        return {name: type(got[name]) in TRACKED_CLASSES for name in changed}

    return tracked


def _text(value: object) -> str:
    """A value as JSON text, as a loop's run records it, or the kind of a value JSON cannot
    hold."""
    try:
        return json.dumps(plain_json(value, tuples=False))
    except (TypeError, ValueError, RecursionError):
        return f"a {type(value).__name__}"
