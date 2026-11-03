"""Each size the solver chooses, held small on the first ask and grown where an unsat rests on it.

Where nothing on the path decides a size, cvc5 may pick the top of its bound: a float's int as a
list's index gives the list a million items, which take seconds to build and run. So each list
length, each dict size and each string leaf's length is held on the first ask to at most
``first_most`` of the input's size of it, 0 for a value the input lacks, in an assertion named
``size!`` and a count when the program asks for a core. An unsat asks for the core, as a float
held finite does (see ``cvc5._held_first``): each hold it names grows ``GROWTH``-fold, and at
``MOST_ITEMS`` it is written no more, so only the cap holds the size. A core that names no hold
makes the unsat the path's. Plan nested-floats-bools, 5.8.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

from pyct.solver.answer_size import MOST_ITEMS
from pyct.solver.declared import Leaves
from pyct.solver.dicts import DictTerms
from pyct.solver.lists import ListTerms, Origin

# what names the assertion that holds a size, before its count. `!` is in no symbol, so the
# name never meets a constant
SIZE = "size!"

# how many times over a hold grows each time an unsat's core names it
GROWTH = 16


def first_most(given: int) -> int:
    """The most a size is held to on the first ask: twice the input's, and eight."""
    return 2 * given + 8


def held_small(
    lists: ListTerms, dicts: DictTerms, seed: Leaves, origin: Origin, *, cores: bool
) -> tuple[list[str], dict[str, tuple[str, int]]]:
    """The holds of a program written from ``origin``, and each by its name (``size_holds``):
    none where the origin holds no size small."""
    if not origin.small:
        return [], {}
    strings = {
        constant: origin.values.get(name)
        for name, constant in seed.constants.items()
        if seed.kinds[name] is str
    }
    return size_holds(sizes(lists, dicts, strings), origin.sizes, cores=cores)


def sizes(lists: ListTerms, dicts: DictTerms, strings: Mapping[str, object]) -> dict[str, int]:
    """Each size the program leaves the solver to choose, by its term, with the input's size of
    it: each list's length, each str item's, each dict's size, each str value's a dict declares,
    and each string leaf's, by its constant in ``strings`` with the input's value."""
    found = {length: lists.origin.get(length, 0) for length in lists.bounded}
    found |= {f"(str.len {term})": 0 for term in lists.holds.strings}
    for tracked in dicts.dicts.values():
        if tracked.sized:
            found[tracked.constant("len")] = len(tracked.shape.keys)
    found |= {f"(str.len {name})": 0 for name, sort in dicts.extra.items() if sort == "String"}
    for constant, value in strings.items():
        found[f"(str.len {constant})"] = len(value) if isinstance(value, str) else 0
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
