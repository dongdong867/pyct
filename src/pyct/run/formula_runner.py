"""A formula in use's runner, which calls its compiled code only in an input's own process, and
the formulas in use as text, as a fresh interpreter gets them with its request.

pyct's process compiles a formula and never runs it, not even its ``def``
statement, as decision
llm-model-written-code-runs-only-in-a-process-of-the-call-s-own says. The
runner holds the compiled code; on its first call, which comes inside an
input's own process at the loop's end, it runs the code's module as a
model-run child does (`pyct.run.model_runs`), with the target's builtins
bound, then calls ``summary`` on the values it is handed. Called in the
process it is told is pyct's own, it raises `FormulaInPyctProcessError`
instead.

A forked input inherits core's table of loops in use (`pyct.core.entry.in_use`)
with each runner in it. A code object does not pickle, so a fresh
interpreter is handed each runner's `FormulaText` instead, read from the
table as its request is made, since formulas come into use and are dropped
during a run. It compiles each text through the compile and form check
pyct's process uses (`pyct.run.summary_form.compiled_formula`), builds the
runner itself, which then has no process to refuse, and fills the table
before its input runs. A text it does not compile leaves its loop out of
the table: that input runs the loop as written, as it would with no formula,
and is still a true input. pyct's process compiled the same text first, so
this does not happen while both run the same pyct.
"""

from __future__ import annotations

import math
import os
import types
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pyct.core.entry.calls_in_use import CallInUse
from pyct.core.entry.in_use import IN_USE, LoopInUse
from pyct.intercept.model_code import Refused
from pyct.intercept.wrap import bound_builtins
from pyct.run.summary_form import SUMMARY, compiled_formula


class FormulaInPyctProcessError(RuntimeError):
    """A formula's runner was called in pyct's own process, which never runs model code."""


@dataclass(frozen=True)
class FormulaText:
    """A formula in use as a fresh interpreter compiles it: its text as the reply wrote it, its
    parameters, the names it gives a value, its loop's or loss site's file, line and column, and
    the file name its code objects carry. A loss site's formula also names the site's downgrade
    and each value going in's parameter by its position (`pyct.core.entry.calls_in_use`); a
    loop's names neither."""

    text: str
    parameters: tuple[str, ...]
    changed: tuple[str, ...]
    place: tuple[str, int, int]
    file: str
    name: str | None = None
    positions: tuple[str | None, ...] | None = None


class FormulaRunner:
    """A formula's call as a loop in use makes it: each parameter's value by name in, each changed
    name's value by name out. The code's module runs on the first call, in the input's process.

    ``home`` is the id of the process the code never runs in: pyct's own, which builds the runner
    a forked input inherits; None in a fresh interpreter, which builds the runner it calls."""

    def __init__(self, code: types.CodeType, text: FormulaText, home: int | None) -> None:
        self.code = code
        self.text = text
        self.home = home
        self.summary: Callable[..., Any] | None = None

    def __call__(self, values: Mapping[str, object]) -> Mapping[str, object]:
        if self.summary is None:
            self.summary = self._defined()
        return self.summary(**values)

    def _defined(self) -> Callable[..., Any]:
        """The formula's function, its module run in a namespace of its own."""
        if os.getpid() == self.home:
            raise FormulaInPyctProcessError("pyct's own process never runs a formula")
        namespace: dict[str, object] = {"__builtins__": bound_builtins(), "math": math}
        exec(self.code, namespace)
        summary = namespace[SUMMARY]
        assert callable(summary)
        return summary


def call_in_use(runner: FormulaRunner) -> CallInUse | None:
    """The loss site in use the runner's formula stands for, or None for a loop's formula."""
    text = runner.text
    if text.name is None or text.positions is None:
        return None
    return CallInUse(text.name, text.positions, runner)


def handed_formulas() -> tuple[FormulaText, ...]:
    """The text of each formula in core's table of loops in use now, for a fresh interpreter."""
    return tuple(
        loop.formula.text for loop in IN_USE.values() if isinstance(loop.formula, FormulaRunner)
    )


def install(formulas: Iterable[FormulaText]) -> None:
    """In a fresh interpreter, before its input runs: put each formula it was handed in core's
    table, compiled here, its runner built here; each text that does not compile is left out."""
    for each in formulas:
        code = compiled_formula(each.text, each.parameters, each.changed, each.file)
        if isinstance(code, Refused):
            continue
        runner = FormulaRunner(code, each, home=None)
        IN_USE[each.place] = LoopInUse(each.parameters, each.changed, runner)
