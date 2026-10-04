"""The text of a path's program, in the order cvc5 reads it."""

from __future__ import annotations

import re
from typing import Protocol

from pyct.core.branch import Branch
from pyct.solver.answer_size import longest_string
from pyct.solver.dicts import DictTerms
from pyct.solver.heads import SORTS
from pyct.solver.lists import ListTerms
from pyct.solver.splits import named_classes

# a symbol or a constant a program line names: a run of what is neither space nor a paren
_SYMBOL = re.compile(r"[^\s()]+")


class Body(Protocol):
    """What a path's written conditions hand the text: their lists and dicts, the parts defined
    once, each bound a form is exact inside, and each fork's assertion."""

    lists: ListTerms
    dicts: DictTerms
    definitions: list[str]
    bounds: list[str]
    bounded: bool

    def assertion(self, fork: Branch) -> str: ...


def program_text(
    prefix: tuple[Branch, ...],
    body: Body,
    declared: list[tuple[str, str]],
    finites: list[str],
    *,
    cores: bool,
) -> str:
    """The program's lines, in the order cvc5 reads them: each leaf and each list's and dict's
    parts declared before any term on them, each split's count a line reads among them as its
    c*, the leaves held finite, each class of characters a line names, the definitions, what
    the lists, the dicts and the path assert, and what to ask for."""
    terms, dicts = body.lists, body.dicts
    lines = ["(set-option :dump-unsat-cores true)"] if cores else []
    lines.append("(set-logic ALL)")
    lines += [f"(declare-const {constant} {sort})" for constant, sort in declared]
    lines += [longest_string(constant) for constant, sort in declared if sort == SORTS[str]]
    lines += [f"(declare-const {name} {sort})" for name, sort in terms.declared.items()]
    lines += dicts.declarations()
    bounds = [f"(assert {bound})" for bound in body.bounds if body.bounded]
    asserted = terms.assertions() + dicts.assertions()
    forks = [body.assertion(fork) for fork in prefix]
    written = [*body.definitions, *bounds, *asserted, *forks]
    counts = terms.splits.defined(written)
    lines += counts + finites + named_classes("\n".join(written)) + written
    lines.append("(check-sat)")
    # a leaf named in none of these lines, nor in what `_read` follows from them, keeps the
    # input's value: a split's count asked as c* names its string in the path, but not in
    # these lines, as origin/v2's plain count never named it
    read = _read(body.definitions, [*counts, *bounds, *asserted, *forks])
    lines += [f"(get-value ({constant}))" for constant, _ in declared if constant in read]
    lines += [f"(get-value ({name}))" for name in [*terms.asked(), *dicts.asked()]]
    return "\n".join(lines) + "\n"


def _read(definitions: list[str], lines: list[str]) -> str:
    """The lines, each definition they name, and each assertion among the definitions that
    names a constant a definition declares, in turn: the text a leaf is read in. A letter read
    of a spelled string, say, names its letter's constant, and the assertion that spells the
    string names the string. An assertion that names no such constant, a split's piece held
    there say, is not followed: it holds on every input that took the path this far. A
    definition is named by a symbol with no space in it."""
    defined = {definition.split()[1]: definition for definition in definitions}
    declared = {
        definition.split()[1]
        for definition in definitions
        if definition.startswith(("(declare-const ", "(define-fun "))
    }
    held: dict[str, list[str]] = {}
    for line in definitions:
        if line.startswith("(assert "):
            for symbol in set(_SYMBOL.findall(line)) & declared:
                held.setdefault(symbol, []).append(line)
    reached: list[str] = []
    seen: set[str] = set()
    pending = list(lines)
    while pending:
        line = pending.pop()
        reached.append(line)
        for symbol in _SYMBOL.findall(line):
            if symbol in defined and symbol not in seen:
                seen.add(symbol)
                pending += [defined[symbol], *held.get(symbol, [])]
    return "\n".join(reached)
