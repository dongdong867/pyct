"""A result that wrote a tracked value in as its text, ``["wrote", result, ["was", x, v]]``
(plan nested-floats-bools, 5.9).

The result's form holds the text the value had, so it is the result only while the value is as
it was: its term is the form where ``x`` is ``v``, and a value of its own anywhere else. The
program holds ``x`` at ``v`` beside it, once however many results wrote it in, in an assertion
named ``STAYS_NAME`` and a count when it asks for a core. So a model keeps the value as it was,
and an unsat that rests on the form names the hold in its core, which no ask frees: that unsat
is unknown, not the path's (``cvc5._held_first``). A path that reads no such result holds
nothing.
"""

from __future__ import annotations

from typing import Protocol

from pyct.core.branch import WROTE, Expression
from pyct.solver.heads import SORTS

# what names the assertion that holds a value written in, before its count. No other name a
# program declares or asserts starts with it
STAYS_NAME = f"{WROTE}!"


class Body(Protocol):
    """What writing such a result needs of the program: its terms and types, the definitions it
    declares names in, and the holds so far."""

    definitions: list[str]
    stays: list[str]

    def term(self, expression: Expression) -> str: ...

    def type_of(self, term: Expression) -> type | None: ...


def wrote(body: Body, result: Expression, was: Expression) -> str:
    """The term of a result that wrote a value in, ``was`` holding that value as it was, and the
    hold noted once."""
    held = body.term(was)
    if held not in body.stays:
        body.stays.append(held)
    written = body.term(result)
    kind = body.type_of(result)
    sort = None if kind is None else SORTS.get(kind)
    if sort is None:
        return written
    other = f"e!{len(body.definitions)}"
    body.definitions.append(f"(declare-const {other} {sort})")
    return f"(ite {held} {written} {other})"


def holds(stays: list[str], *, cores: bool) -> list[str]:
    """The assertion of each hold, named for a count when the program asks for a core."""
    if not cores:
        return [f"(assert {held})" for held in stays]
    return [f"(assert (! {held} :named {STAYS_NAME}{n}))" for n, held in enumerate(stays)]
