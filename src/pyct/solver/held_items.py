"""A path's float items held finite on the first ask, and what an unsat frees.

Decision float-finite-first-frees-the-core-s-leaves-and-lists: NaN, which a person would not
pick, is an answer cvc5 is free to give for any float the path does not hold. So each float read
of a list the seed names and each float value a dict declares is held finite on the first ask,
in an assertion named for the symbol of its list or dict and a count, `finite!arg.xs!0`. A core
that names any one of them frees that whole list or dict; the others stay held.
"""

from __future__ import annotations

from collections.abc import Collection, Mapping

from pyct.binding.shapes import ListShape
from pyct.core.branch import Branch
from pyct.solver import floats
from pyct.solver.dag import Node, distinct
from pyct.solver.declared import Leaves, symbols
from pyct.solver.dicts import DictTerms, TrackedDict
from pyct.solver.joined import joined
from pyct.solver.lists import ListTerms, Origin, TrackedList
from pyct.solver.str_joins import expanded


def path_of(
    prefix: tuple[Branch, ...], leaves: Mapping[str, type], origin: Origin
) -> tuple[tuple[Branch, ...], list[Node], dict[int, int], dict[str, str]]:
    """The path as written: joins spelled out, pieces side by side as one, each distinct part in
    order with how many places hold it, and each leaf, list and dict it names by symbol."""
    shapes = origin.shapes
    seed = Leaves(kinds=leaves, constants={}, lists=shapes, dicts=origin.dicts)
    prefix = expanded(prefix, seed.holds)
    listed = ListTerms(shapes, {}).listed(distinct(prefix, seed.holds)[0])
    containers = (TrackedList, TrackedDict)
    prefix = joined(
        prefix, seed.holds, lambda part: id(part) in listed or seed.kind(part) in containers
    )
    order, holding = distinct(prefix, seed.holds)
    return prefix, order, holding, symbols(prefix, order, seed)


def float_leaves(
    prefix: tuple[Branch, ...],
    leaves: Mapping[str, type],
    lists: Mapping[str, ListShape] | Origin | None = None,
) -> frozenset[str]:
    """What a fork of the prefix names that its first ask holds finite: each float leaf, each
    list that can hold a float, and each dict that can."""
    origin = lists if isinstance(lists, Origin) else Origin(shapes=lists or {})
    containers = {
        name
        for shapes in (origin.shapes, origin.dicts)
        for name, shape in shapes.items()
        if shape.holds_floats
    }
    if float not in leaves.values() and not containers:
        return frozenset()
    _, _, _, named = path_of(prefix, leaves, origin)
    return frozenset(name for name in named if leaves.get(name) is float or name in containers)


def finite_items(
    lists: ListTerms, dicts: DictTerms, finite: Collection[str], *, cores: bool
) -> list[str]:
    """The assertion that holds each float a list or a dict in ``finite`` reads finite, named
    for its symbol and a count when the program asks for a core."""
    names = holders(lists, dicts)
    terms = [*lists.holds.floats.items(), *dicts.float_values.items()]
    held = [(term, symbol) for term, symbol in terms if names.get(symbol) in finite]
    return [
        floats.held_finite(term, f"{symbol}!{count}" if cores else None)
        for count, (term, symbol) in enumerate(held)
    ]


def holders(lists: ListTerms, dicts: DictTerms) -> dict[str, str]:
    """Each list and dict of the path by its symbol."""
    named = {symbol: name for name, symbol in lists.symbols.items()}
    return named | {found.symbol: found.name for found in dicts.dicts.values()}
