"""The loss sites in use, which an upper layer fills, and what every formula in use shares: the
answer's name, the copy of a list or dict going in that a formula reads, and the marks on the
forks a formula's values reach.

An upper layer puts each loss site in use in `CALLS_IN_USE`, by its file,
line and column, before an input starts; `pyct.core.entry.calls_in_use`
reads it then. While a formula runs (`USING.forming`), each fork it
records is marked ``summary``, and so is a later fork of the input whose
condition holds the term of a value a formula gave there (`summed`), so
that an input aimed at one says the formula gave it. A formula value
whose term is a bare name, a parameter handed back as it is, has no term
of its own, and the forks that read it are not marked. `start` and
`forget` clear what the marks know for each input.
"""

from __future__ import annotations

import copy
import dataclasses
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from typing import cast

from pyct.core.dicts.dicts import ConcolicDict
from pyct.core.entry.plain_copy import plain_copy
from pyct.core.foundation.branch import Branch, Expression
from pyct.core.lists.lists import ConcolicList
from pyct.core.numbers.ints import ConcolicInt

type _Place = tuple[str, int, int]

# the one name a loss site's formula gives a value for
ANSWER = "answer"


@dataclass(frozen=True)
class CallInUse:
    """A loss site's formula (`pyct.core.entry.calls_in_use`): the name of the downgrade it
    stands for, each value going in's parameter by its position, None for a constant the formula
    does not take, and the call that takes each parameter's value by name and answers
    ``answer``'s."""

    name: str
    positions: tuple[str | None, ...]
    formula: Callable[[Mapping[str, object]], Mapping[str, object]]


# the loss sites in use, by the file, line and column of each, which an upper layer fills
CALLS_IN_USE: dict[_Place, CallInUse] = {}


class _Using:
    """The live input's marks: whether a formula is running, and what `summed` knows of the
    input's terms."""

    __slots__ = ("clean", "forming", "reads")

    def __init__(self) -> None:
        self.clear()

    def clear(self) -> None:
        self.forming = False
        # each part of a term known to be or to hold the term of a value a formula gave in the
        # input, by its id, the part kept so that its id stays its own
        self.reads: dict[int, list[Expression]] = {}
        # the ids of the parts known to hold none, each reachable from a fork the input keeps
        self.clean: set[int] = set()


USING = _Using()


def start() -> None:
    """An input goes live: no fork reads a value a formula gave yet."""
    USING.clear()


def forget() -> None:
    """The live input ends: what the marks knew of it goes."""
    USING.clear()


def gave(values: Iterable[object]) -> None:
    """Keep the term of each tracked value a formula gave, for `summed`. A walk that finds no term
    adds every part it reached to the clean parts, so a clean part can hold a term kept now only
    when that term is itself clean, as when the formula hands back a term it was given; only
    then is no part known clean any more."""
    terms = [term for each in values if isinstance(term := _term(each), list)]
    USING.reads.update((id(term), term) for term in terms)
    if any(id(term) in USING.clean for term in terms):
        USING.clean.clear()


def _term(value: object) -> Expression:
    return cast(ConcolicInt, value).expression


def summed(fork: Branch) -> Branch:
    """The fork, marked ``summary`` when a formula is running, so that it recorded the fork, or
    when its condition holds, as the very list, the term of a value a formula gave in the
    input; else the fork itself. A part found to hold no such term is not walked again in the
    input, unless a later formula hands back a term it was given that is such a part."""
    reads = USING.reads
    if not USING.forming and not reads:
        return fork
    if USING.forming or _reads_a_formula(fork.expression, reads, USING.clean):
        return dataclasses.replace(fork, summary=True)
    return fork


def _reads_a_formula(
    expression: Expression, reads: dict[int, list[Expression]], clean: set[int]
) -> bool:
    """Whether the expression is or holds a part ``reads`` keeps; a part found to hold one is kept
    too, and the parts of an expression found to hold none join ``clean``."""
    if not isinstance(expression, list):
        return False
    seen: set[int] = set()
    pending: list[list[Expression]] = [expression]
    while pending:
        part = pending.pop()
        key = id(part)
        if key in reads:
            reads[id(expression)] = expression
            return True
        if key in clean or key in seen:
            continue
        seen.add(key)
        pending.extend(each for each in part if isinstance(each, list))
    clean.update(seen)
    return False


def as_it_went_in(value: object) -> object:
    """A list or dict going in as a copy of the list or dict itself, one level deep, taken each time
    a watched call in a file that holds a loss site in use is given it: a call that adds, removes
    or replaces its items leaves the copy as it went in. A tracked one's copy is tracked by the
    same form and records no fork. One with no form, or whose length is not the one pyct last
    saw, gets a plain copy (`plain_copy`), which runs none of the methods the target wrote for
    its containers, nor a hash or equality it wrote for its keys, records nothing unless a
    standard-library hash runs a key's own methods, and leaves the target's own as it is. A
    tracked copy costs about 4 microseconds for a list of 100 items and 30 for 1,000. A plain
    copy's cost grows with every item it reaches through lists, tuples, dicts, sets and
    frozensets: about 9 for a list of 100 ints and 85 for 1,000, about 1 more for each tuple or
    list it holds and 2.5 for each dict of three keys, as 1,300 for a heap of 1,000 tuples, and
    400 for a list that holds one list of 10,000 plain ints. Any other value as it is."""
    kind = type(value)
    if kind is ConcolicList:
        items = cast(ConcolicList, value)
        current = items.expression is not None and items.length() == len(items.shadow)
        return copy.copy(items) if current else plain_copy(items)
    if kind is ConcolicDict:
        pairs = cast(ConcolicDict, value)
        current = pairs.expression is not None and pairs.size() == len(pairs.shadow)
        return copy.copy(pairs) if current else plain_copy(pairs)
    if kind is list or kind is dict:
        return copy.copy(value)
    return value
