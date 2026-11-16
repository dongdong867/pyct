"""A run's loops in use: whether a loop's checked formula can come into use, the runner each
formula in use is called through, and core's table of loops in use (`pyct.core.entry.in_use`),
which each input forked from pyct's process inherits.

pyct's process compiles a formula (`pyct.run.summary_checks.formula_code`)
and never runs it, not even its ``def`` statement, as decision
llm-model-written-code-runs-only-in-a-process-of-the-call-s-own says. The
runner holds the compiled code; on its first call, which comes inside an
input's own process at the loop's end, it runs the code's module as a
model-run child does (`pyct.run.model_runs`), with the target's builtins
bound, then calls ``summary`` on the values it is handed. Called in the
process that built it, it raises `FormulaInPyctProcessError` instead.

A formula comes into use when the run's inputs run in a process of their
own, the loop's own code holds no ``return``, ``yield`` or ``await``, and
every changed value its complete runs recorded is an int, float, str or bool.
"""

from __future__ import annotations

import ast
import json
import math
import os
import types
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pyct.core.entry.in_use import IN_USE, LoopInUse
from pyct.core.foundation.branch import Site
from pyct.intercept.wrap import bound_builtins
from pyct.results.pieces import FUNCTIONS, SCOPES, Piece, pieces, proper
from pyct.run.summary_checks import CompleteRun
from pyct.run.summary_form import SUMMARY

# why a formula is not used: the run's inputs run in pyct's own process
IN_PYCT_S_PROCESS = "inputs run in pyct's own process"
# what a loop's own code holds that leaves its frame part way through a run, by its node
_LEAVING: dict[type[ast.AST], str] = {
    ast.Return: "a return",
    ast.Yield: "a yield",
    ast.YieldFrom: "a yield",
    ast.Await: "an await",
}
# the kinds of the values a loop in use can change
_KINDS = (int, float, str, bool)


class FormulaInPyctProcessError(RuntimeError):
    """A formula's runner was called in pyct's own process, which never runs model code."""


@dataclass(frozen=True)
class FormulaInUse:
    """A loop's formula in use: its text as the reply wrote it, its parameters, the names it gives
    a value, the loop's site, the file name its code objects carry, and its code as pyct's process
    compiled it."""

    text: str
    parameters: tuple[str, ...]
    changed: tuple[str, ...]
    site: Site
    file: str
    code: types.CodeType


class FormulaRunner:
    """A formula's call as a loop in use makes it: each parameter's value by name in, each changed
    name's value by name out. The code's module runs on the first call, in the input's process."""

    def __init__(self, code: types.CodeType) -> None:
        self.code = code
        # the process that built the runner, pyct's own, where the code never runs
        self.home = os.getpid()
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


class LoopsInUse:
    """A run's formulas in use, by their loops' sites, each in core's table until `close`."""

    def __init__(self) -> None:
        self.formulas: dict[Site, FormulaInUse] = {}

    def use(self, formula: FormulaInUse) -> None:
        """Put the formula's loop in use from the next input on."""
        site = formula.site
        self.formulas[site] = formula
        runner = FormulaRunner(formula.code)
        IN_USE[_place(site)] = LoopInUse(formula.parameters, formula.changed, runner)

    def close(self) -> None:
        """Take each of the run's loops out of core's table, as the run ends."""
        for site in self.formulas:
            IN_USE.pop(_place(site), None)
        self.formulas.clear()


def unused_because(
    site: Site, runs: Sequence[CompleteRun], changed: Sequence[str], isolated: bool
) -> str | None:
    """Why the checked formula of the loop at ``site`` does not come into use, or None when it
    does. ``isolated`` says whether the run's inputs run in a process of their own."""
    if not isolated:
        return IN_PYCT_S_PROCESS
    found = statement_at(site)
    if found is None:
        return "the loop's file no longer holds it"
    leaving = leaving_by(found[0])
    if leaving is not None:
        return f"the loop holds {leaving}"
    for each in runs:
        for value in each.run.changed:
            if value.name in changed and not _of_kinds(value.value):
                return f"{value.name} is not an int, float, str or bool"
    return None


def statement_at(site: Site) -> tuple[ast.stmt, Piece] | None:
    """The piece of a function in ``site``'s file at its line and column, with its statement, as
    the file reads now; None when it does not read or parse, or holds none there."""
    try:
        with open(site.file, encoding="utf-8") as opened:
            tree = ast.parse(opened.read(), filename=site.file)
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    for node in ast.walk(tree):
        if isinstance(node, FUNCTIONS):
            for statement, piece in pieces(node):
                if (piece.line, piece.col) == (site.line, site.col):
                    return statement, piece
    return None


def leaving_by(statement: ast.stmt) -> str | None:
    """What the piece's own code holds that leaves its frame part way through a run, the first
    met in the order written: a return, a yield, or an await, an ``async for``'s and an async
    comprehension's included. A function, lambda or class defined inside it is its own."""
    if isinstance(statement, ast.AsyncFor):
        return _LEAVING[ast.Await]
    pending = list(reversed(proper(statement)))
    while pending:
        node = pending.pop()
        if isinstance(node, SCOPES):
            continue
        if isinstance(node, ast.comprehension) and node.is_async:
            return _LEAVING[ast.Await]
        leaving = _LEAVING.get(type(node))
        if leaving is not None:
            return leaving
        pending.extend(reversed(list(ast.iter_child_nodes(node))))
    return None


def _of_kinds(text: str) -> bool:
    """Whether a recorded value's JSON text holds an int, float, str or bool."""
    try:
        return isinstance(json.loads(text), _KINDS)
    except ValueError:
        return False


def _place(site: Site) -> tuple[str, int, int]:
    return (site.file, site.line, site.col)
