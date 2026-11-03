"""Each list length and dict size the solver chooses, held small on the first ask and grown
where an unsat rests on it.

Where nothing on the path decides a length, cvc5 may pick the top of its bound: a float's int as
a list's index gives the list a million items, which take seconds to build and run. So each list
length, and each dict size a program declares, is held on the first ask to at most
``first_most`` of the input's size of it, 0 for a value the input lacks, in an assertion named
``size!`` and a count when the program asks for a core. An unsat asks for the core, as a float
held finite does (see ``cvc5._held_first``): each hold it names grows ``GROWTH``-fold, and at
``MOST_ITEMS`` it is written no more, so only the cap holds the size. A core that names no hold
makes the unsat the path's. Plan nested-floats-bools, 5.8.

The input's size of a list is its own length, and for a row read where no shape says which, at
a tracked index or from the end, the longest of the input's rows.

A string keeps only its cap: held small, a fork only a longer string takes can leave cvc5
unable to prove the held ask unsat within its limit, a string split into twenty pieces say.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

from pyct.solver.answer_size import MOST_ITEMS
from pyct.solver.dicts import DictTerms
from pyct.solver.lists import ListTerms, Origin

# what names the assertion that holds a size, before its count. No other name a program declares
# or asserts starts with it, so the name never meets a constant or another hold
SIZE = "size!"

# how many times over a hold grows each time an unsat's core names it
GROWTH = 16


def first_most(given: int) -> int:
    """The most a size is held to on the first ask: twice the input's, and eight."""
    return 2 * given + 8


def held_small(
    lists: ListTerms, dicts: DictTerms, origin: Origin, *, cores: bool
) -> tuple[list[str], dict[str, tuple[str, int]]]:
    """The holds of a program written from ``origin``, and each by its name (``size_holds``):
    none where the origin holds no size small."""
    if not origin.small:
        return [], {}
    return size_holds(sizes(lists, dicts), origin.sizes, cores=cores)


def sizes(lists: ListTerms, dicts: DictTerms) -> dict[str, int]:
    """Each size the program leaves the solver to choose, by its term, with the input's size of
    it: each list's length, and each dict's size where the program declares one."""
    found = dict(lists.bounded)
    for tracked in dicts.dicts.values():
        if tracked.sized:
            found[tracked.constant("len")] = len(tracked.shape.keys)
    return found


def size_holds(
    found: Mapping[str, int], grown: Mapping[str, int], *, cores: bool
) -> tuple[list[str], dict[str, tuple[str, int]]]:
    """The assertion that holds each size found to its most: its first, or what a core grew it
    to in ``grown``; none for a size held to ``MOST_ITEMS`` or more. Also each hold by its name,
    with its term and its most, named for a count when the program asks for a core."""
    lines: list[str] = []
    named: dict[str, tuple[str, int]] = {}
    for term, given in found.items():
        most = grown.get(term, first_most(given))
        if most >= MOST_ITEMS:
            continue
        name = f"{SIZE}{len(named)}"
        named[name] = (term, most)
        held = f"(<= {term} {most})"
        lines.append(f"(assert (! {held} :named {name}))" if cores else f"(assert {held})")
    return lines, named


def grown_by(holds: Mapping[str, tuple[str, int]], core: Collection[str]) -> dict[str, int]:
    """Each size a core names a hold of, by its term, with the most it is held to next."""
    return {holds[name][0]: holds[name][1] * GROWTH for name in core if name in holds}
