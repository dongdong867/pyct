"""Which `in` and `is` tests read their value the other way from the forks recorded there.

A flow reads a test's sides as the value its jump tests. pyct records a fork
of its own at an `in` or an `is`, and the two can differ. pyct folds a `not`
over one compare into it on every release, and records `x not in c` for
``not x in c``, where 3.14 tests `in` and jumps the other way. An element
search records `==` forks, whose true side is the `in`'s. An `is` against a
bool records the other side's own truth, so ``x is not True`` holds on its
false side. Each such test's sides are read as the forks recorded there, and
a test with no fork recorded keeps its own.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from pyct.results.way import Flow, Fork, Step

# a site, as a fork records it: its line and column
type At = tuple[int, int]
# one input as the sense reads it: the lines it covered, and its forks
type Seen = tuple[frozenset[int], tuple[Fork, ...]]


def against_the_forks(
    flow: Flow, heads: Mapping[At, frozenset[str]], seen: list[Seen]
) -> list[int]:
    """The side nodes of every `in` and `is` test that reads the other way from its forks.

    ``heads`` holds the operator of each fork recorded at a site. At an `in`
    the forks say: a `not in` fork is negated, and any other, an `in` or an
    element's `==`, is not. At an `is` the fork is its operand's, whose sense
    depends on the bool it is compared with, so the inputs say: each input
    that recorded one side of the fork there, and covered a line only one of
    the test's sides leads to, shows whether the two agree.
    """
    tests: dict[At, list[tuple[int, Step]]] = {}
    for node, step in flow.pace.each(flow.sides().items()):
        if step.reads is not None and (step.line, step.col) in heads:
            tests.setdefault((step.line, step.col), []).append((node, step))
    marks: list[frozenset[int]] | None = None
    swapped: list[int] = []
    for site, sides in flow.pace.each(tests.items()):
        name, negated = sides[0][1].reads or ("", False)
        if name == "CONTAINS_OP":
            other = ("not in" in heads[site]) != negated
        else:
            marks = marks if marks is not None else [flow.marked(lines, ()) for lines, _ in seen]
            other = _shown_other(site, sides, seen, marks)
        swapped.extend(node for node, _ in sides if other)
    return swapped


def _shown_other(
    site: At, sides: list[tuple[int, Step]], seen: list[Seen], marks: list[frozenset[int]]
) -> bool:
    """Whether every input that shows both the fork's side and the test's reads them apart."""
    found: set[bool] = set()
    for (_, forks), marked in zip(seen, marks, strict=True):
        taken = {
            taken for line, col, taken, raising in forks if (line, col) == site and not raising
        }
        passed = [step.side for node, step in sides if node in marked]
        if len(taken) == 1 and len(passed) == 1:
            found.add(passed[0] != taken.pop())
    return found == {True}


def heads_of(forks: Iterable[tuple[At, object]]) -> dict[At, frozenset[str]]:
    """The operator of each fork at each site: an expression's head, or its text when it is one."""
    found: dict[At, set[str]] = {}
    for site, expression in forks:
        head = expression[0] if isinstance(expression, list) and expression else expression
        found.setdefault(site, set()).add(str(head))
    return {site: frozenset(each) for site, each in found.items()}
