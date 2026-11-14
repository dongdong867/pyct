"""A loop's summary as the model writes it: the answer's form the request gives, the formula the
reply's code writes once it passes the form check (`pyct.run.summary_form`), and the two checks
the formula runs through before it is kept.

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
from pyct.run.model_runs import CannotFork, ModelCall, ModelRun, run_model
from pyct.run.process import InputStartError
from pyct.run.summary_form import (
    FOLLOW,
    FORMULA_CALLS,
    MOST_STATEMENTS,
    PAST,
    RUNS,
    SUMMARY,
    TRACKED,
    FormCheck,
)

# the seconds each check's child may take at most
CHECK_SECONDS = 2.0
# why no check could run beside a second thread of pyct's process
CANNOT_FORK = "cannot fork"


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
    code = compile_model_code(text, file, FormCheck(tuple(parameters), tuple(changed)))
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
    names = {"math": math, RUNS: _runner(values, changed)}
    ran = _child(ModelCall(code, PAST, {}, names), until)
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
    names = {"math": math, TRACKED: _tracker(plain, changed)}
    ran = _child(ModelCall(code, FOLLOW, leaves, names), until)
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
