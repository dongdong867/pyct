"""A run's loops in use: whether a loop's checked formula can come into use, and core's table of
loops in use (`pyct.core.entry.in_use`), which each input forked from pyct's process inherits and
a fresh interpreter is handed as text (`pyct.run.formula_runner`).

pyct's process compiles a formula (`pyct.run.summary_checks.formula_code`)
and never runs it; each loop in use calls its formula through a
`FormulaRunner`, which runs the code only in an input's own process.

A formula comes into use when the run's inputs run in a process of their
own, the loop's own code holds no ``return``, ``yield`` or ``await``, and
every changed value its complete runs recorded is an int, float, str or bool.
It goes out of use when an input's run of the loop drops it, or once the
run's inputs run in pyct's own process.
"""

from __future__ import annotations

import ast
import json
import os
import types
from collections.abc import Sequence

from pyct.core.entry.in_use import IN_USE, LoopInUse
from pyct.core.foundation.branch import DropReason, FormulaDrop, Site
from pyct.results.pieces import FUNCTIONS, SCOPES, Piece, pieces, proper
from pyct.run.formula_runner import FormulaRunner, FormulaText
from pyct.run.summary_checks import CompleteRun

# why a formula is not used: the run's inputs run in pyct's own process
IN_PYCT_S_PROCESS = "inputs run in pyct's own process"
# the return, yield and await a loop's own code can hold, by their nodes, in plain words
_LEAVING: dict[type[ast.AST], str] = {
    ast.Return: "a return",
    ast.Yield: "a yield",
    ast.YieldFrom: "a yield",
    ast.Await: "an await",
}
# the kinds of the values a loop in use can change
_KINDS = (int, float, str, bool)
# each other kind a value's JSON text reads as, in plain words
_OTHER_KINDS: dict[type, str] = {list: "a list", dict: "a dict", type(None): "None"}


class LoopsInUse:
    """A run's loops in use, by their sites, each in core's table until `close`."""

    def __init__(self) -> None:
        self.sites: set[Site] = set()

    def use(self, text: FormulaText, code: types.CodeType) -> None:
        """Put the formula's loop in use from the next input on: its text, and its code as pyct's
        process compiled it."""
        self.sites.add(Site(*text.place))
        runner = FormulaRunner(code, text, os.getpid())
        IN_USE[text.place] = LoopInUse(text.parameters, text.changed, runner)

    def stop(self, site: Site) -> None:
        """Take the loop at ``site`` out of use from the next input on."""
        self.sites.discard(site)
        IN_USE.pop(place_of(site), None)

    def close(self) -> None:
        """Take each of the run's loops out of core's table, as the run ends."""
        for site in self.sites:
            IN_USE.pop(place_of(site), None)
        self.sites.clear()


def dropped_because(drop: FormulaDrop) -> str:
    """Why an input's run of a loop dropped its formula, in plain words, each value its JSON
    text: the loop's value and the formula's, the raise's type, or the name it gave no value."""
    if drop.reason is DropReason.MISMATCH:
        return f"{drop.name} was {drop.value}, the formula gave {drop.got}"
    if drop.reason is DropReason.RAISED:
        return f"the formula raised {drop.got}"
    return f"the formula gave no {drop.name}"


def unused_because(
    site: Site, runs: Sequence[CompleteRun], changed: Sequence[str], isolated: bool
) -> str | None:
    """Why the checked formula of the loop at ``site`` does not come into use, or None when it
    does. ``isolated`` says whether the run's inputs run in a process of their own."""
    never = never_used_because(site, isolated)
    if never is not None:
        return never
    return kinds_unused_because(runs, changed)


def kinds_unused_because(runs: Sequence[CompleteRun], changed: Sequence[str]) -> str | None:
    """Why a checked formula does not come into use by what its runs recorded, or None when it
    may: a changed value of one of them is not an int, float, str or bool."""
    for each in runs:
        for value in each.run.changed:
            kind = _kind(value.value) if value.name in changed else None
            if kind is not None:
                return f"{value.name} is {kind}"
    return None


def never_used_because(site: Site, isolated: bool) -> str | None:
    """Why no formula of the loop at ``site`` could come into use now, whatever its runs
    recorded, or None when one could: the run's inputs run in pyct's own process, the loop's
    file no longer holds it, or the loop's own code holds a return, yield or await."""
    if not isolated:
        return IN_PYCT_S_PROCESS
    found = statement_at(site)
    if found is None:
        return "the loop's file no longer holds it"
    leaving = leaving_by(found[0])
    if leaving is not None:
        return f"the loop holds {leaving}"
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
    """The first return, yield or await the piece's own code holds, in the order written, an
    ``async for``'s and an async comprehension's await included, or None when it holds none. A
    function, lambda or class defined inside it is its own."""
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


def _kind(text: str) -> str | None:
    """What a recorded value's JSON text holds, in plain words, when it is not an int, float,
    str or bool: ``a list``, ``a dict`` or ``None``, and ``unreadable`` for text JSON does not
    read; None when it is one of those four."""
    try:
        value = json.loads(text)
    except ValueError:
        return "unreadable"
    if isinstance(value, _KINDS):
        return None
    return _OTHER_KINDS[type(value)]


def place_of(site: Site) -> tuple[str, int, int]:
    """The site as core's table keys a loop in use: its file, line and column."""
    return (site.file, site.line, site.col)
