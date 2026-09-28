"""The text of a path's program, in the order cvc5 reads it."""

from __future__ import annotations

from typing import Protocol

from pyct.core.branch import Branch
from pyct.solver.answer_size import longest_string
from pyct.solver.dicts import DictTerms
from pyct.solver.heads import SORTS
from pyct.solver.lists import ListTerms
from pyct.solver.splits import named_classes


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
    parts declared before any term on them, each split's count a line reads among them, the
    leaves held finite, each class of characters a line names, the definitions, each such
    count's tie to its pieces, what the lists, the dicts and the path assert, and what to ask
    for."""
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
    counts, ties = terms.splits.tied([*body.definitions, *bounds, *asserted, *forks])
    written = [*body.definitions, *ties, *bounds, *asserted, *forks]
    lines += counts + finites + named_classes("\n".join(written)) + written
    lines.append("(check-sat)")
    lines += [f"(get-value ({constant}))" for constant, _ in declared]
    lines += [f"(get-value ({name}))" for name in [*terms.asked(), *dicts.asked()]]
    return "\n".join(lines) + "\n"
