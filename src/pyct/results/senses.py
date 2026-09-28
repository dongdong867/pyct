"""How each `in` and `is` test's sides read, the same on every release.

A flow reads a test's sides as the value its jump tests, and releases
compile that value differently: 3.14 tests `in` for ``not x in c`` and
jumps the other way, where 3.12 and 3.13 test `not in`. So each test's sides
are read in one sense, from the compare the code tests (`blocks.Reads`) and,
where the code cannot say, the forks recorded at its site:

- an `in` in the `in` sense, unless every membership fork recorded there
  is a `not in`, which pyct records for a `not` it folds: then in that sense;
- an `is` with no fork recorded there in the `is` sense;
- an `is` against a True or False the code loads, where a fork was
  recorded, in the sense of that fork, its operand's truth: ``x is True``
  holds when the operand does, ``x is False`` when it does not;
- any other `is`, as against a name bound to bools, as the inputs show it:
  each input that recorded one side of a fork there, and covered a line only
  one of the test's sides leads to, says whether the two agree. With none,
  or inputs that disagree, in the `is` sense.
"""

from __future__ import annotations

import functools
from collections.abc import Iterable, Mapping

from pyct.results.blocks import Reads
from pyct.results.graphs import Pace
from pyct.results.way import Flow, Fork, Step

# a site, as a fork records it: its line and column
type At = tuple[int, int]
# one input as the sense reads it: the lines it covered, and its forks
type Seen = tuple[frozenset[int], tuple[Fork, ...]]
# a test's two sides: each node and its step
type Sides = list[tuple[int, Step]]

# the heads a membership test's forks carry: its own, and an element search's
_MEMBERSHIP = frozenset({"in", "not in", "=="})


def against_the_forks(
    flow: Flow, heads: Mapping[At, frozenset[str]], seen: list[Seen]
) -> list[int]:
    """The side nodes of every `in` and `is` test whose sides read the other way from its value.

    ``heads`` holds the operator of each fork recorded at each site. Each test
    is decided on its own, so two links of one chain at one site keep theirs.
    """
    tests: dict[tuple[At, Reads], Sides] = {}
    for node, step in flow.pace.each(flow.sides().items()):
        if step.reads is not None:
            tests.setdefault(((step.line, step.col), step.reads), []).append((node, step))
    # the inputs are asked only of an `is` against a name, and read only at those tests' sites
    named = {site for site, reads in tests if _asks_inputs(reads, heads.get(site, frozenset()))}
    shown = _Shown(flow, seen, frozenset(named))
    swapped: list[int] = []
    for (site, reads), sides in flow.pace.each(tests.items()):
        if _other_way(reads, heads.get(site, frozenset()), shown, site, sides):
            swapped.extend(node for node, _ in sides)
    return swapped


def _other_way(reads: Reads, heads: frozenset[str], shown: _Shown, site: At, sides: Sides) -> bool:
    """Whether a test's sides read the other way from the value its jump tests."""
    if reads.name == "CONTAINS_OP":
        return (heads & _MEMBERSHIP == {"not in"}) != reads.negated
    if not heads:
        return reads.negated
    if not _asks_inputs(reads, heads):
        # the fork is the operand's truth, which `is False` and `is not True` read the other way
        return (reads.flag is False) != reads.negated
    agrees = shown.agree(site, sides)
    return reads.negated if agrees is None else not agrees


def _asks_inputs(reads: Reads, heads: frozenset[str]) -> bool:
    """Whether the inputs decide a test: an `is` where a fork was recorded, against something
    other than a True or False the code loads."""
    return reads.name == "IS_OP" and reads.flag is None and bool(heads)


class _Shown:
    """Each input's forks at the sites asked of, and the sides its lines alone prove, each
    found once, when first asked."""

    def __init__(self, flow: Flow, seen: list[Seen], sites: frozenset[At]) -> None:
        self.flow = flow
        self.seen = seen
        self.sites = sites
        self.marks: dict[int, frozenset[int]] = {}

    @functools.cached_property
    def inputs(self) -> list[tuple[frozenset[int], dict[At, set[bool]]]]:
        pace = self.flow.pace
        return [
            (lines, _taken_at(forks, self.sites, pace)) for lines, forks in pace.each(self.seen)
        ]

    def agree(self, site: At, sides: Sides) -> bool | None:
        """Whether every input that shows both reads the fork's side as the test's, or None when
        none shows both or they disagree."""
        found: set[bool] = set()
        for index, (lines, taken_at) in enumerate(self.flow.pace.each(self.inputs)):
            fork_sides = taken_at.get(site, set())
            if len(fork_sides) != 1:
                continue
            if index not in self.marks:
                self.marks[index] = self.flow.marked(lines, ())
            passed = [step.side for node, step in sides if node in self.marks[index]]
            if len(passed) == 1:
                found.add(passed[0] in fork_sides)
        return found.pop() if len(found) == 1 else None


def _taken_at(forks: Iterable[Fork], sites: frozenset[At], pace: Pace) -> dict[At, set[bool]]:
    """The sides an input's forks took at each of the sites, raising forks aside."""
    found: dict[At, set[bool]] = {}
    for line, col, taken, raising in pace.each(forks):
        if not raising and (line, col) in sites:
            found.setdefault((line, col), set()).add(taken)
    return found


def heads_of(forks: Iterable[tuple[At, object]]) -> dict[At, frozenset[str]]:
    """The operator of each fork at each site: an expression's head, or its text when it is one."""
    found: dict[At, set[str]] = {}
    for site, expression in forks:
        head = expression[0] if isinstance(expression, list) and expression else expression
        found.setdefault(site, set()).add(str(head))
    return {site: frozenset(each) for site, each in found.items()}
