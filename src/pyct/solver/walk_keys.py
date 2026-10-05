"""A dict's walk keys in a path, written for each ask (let-the-solver-choose-a-small-dict-s-walk-
key).

A walk key, `["key", A, i]`, is the key a walk of the dict A reads at pass i (see
``core.dict_walk_keys``). The first ask, and the ask without places, write each one as the key the
input holds at that pass, so they are the programs a walk of plain keys gives. The ask with
chosen keys (``opened``) leaves the key to the solver at each pass a fork names, unless a fact
keeps it where the input had it: each such key is a leaf the solver chooses, and every pass up
to the last one a fork or a fact names is held in its order (``Order``), so the answer lists
those keys first and Python's walk of it reads each one at its pass. A dict whose path keeps a
place no walk key names, a walk from the last, popitem or a later walk's, is written with its
input's keys in that ask too.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import replace

from pyct.binding.bind import access_name
from pyct.binding.shapes import DictShape
from pyct.core.branch import Branch, Expression, Fact
from pyct.core.dict_walk_keys import MOST_KEYS
from pyct.core.walk_key_compares import WALK_KEY
from pyct.solver.dict_keys import key_term

# a dict's name and a pass of its walk
type Pass = tuple[str, int]

_NONE: frozenset[Pass] = frozenset()


# one dict's walk in the ask with chosen keys: for each pass up to the last its path names, the
# leaf the solver chooses its key by, or None where the input's key stays, and the input's key
type Order = tuple[tuple[str | None, object], ...]


class UnwrittenError(ValueError):
    """A walk key whose dict or pass the input does not hold."""


def walk_key(part: Expression) -> Pass | None:
    """The dict and the pass a part names, when it is a walk key."""
    if not (isinstance(part, list) and len(part) == 3 and part[0] == WALK_KEY):
        return None
    dict_part, at = part[1], part[2]
    name = dict_part if isinstance(dict_part, str) else access_name(dict_part)
    return None if name is None or type(at) is not int else (name, at)


def leaf(walked: Pass) -> str:
    """The name of the leaf a chosen walk key is: its expression as JSON, as an access's is."""
    name, at = walked
    return json.dumps([WALK_KEY, name, at])


class Walks:
    """What a path names of its dicts' walk keys, and the path written for each ask."""

    def __init__(self, prefix: tuple[Branch | Fact, ...], dicts: Mapping[str, DictShape]) -> None:
        self.dicts = dicts
        self._below: dict[int, frozenset[Pass]] = {}
        # each pass a fork names, a fact or a fork names, and a fact keeps at the input's key
        self.forked: set[Pass] = set()
        self.named: set[Pass] = set()
        self.pinned: set[Pass] = set()
        # each dict whose path keeps a place no walk key names, and each whose walk handed out
        # a walk key a step names, a place among them
        self.closed: set[str] = set()
        self.walked: set[str] = set()
        for step in prefix:
            self._learn(step)
        self.walked |= {name for name, _ in self.named}

    def _learn(self, step: Branch | Fact) -> None:
        named = self._passes(step.expression)
        self.named |= named
        if isinstance(step, Branch):
            self.forked |= named
            return
        if _pins(step) and named:
            self.pinned |= named
        place = step.place
        if isinstance(place, list) and place[:1] == ["given"]:
            place = place[1]
        if not isinstance(place, list) or len(place) < 2:
            return
        walked = walk_key(place[2]) if len(place) == 3 and place[0] == "walked" else None
        if walked is not None:
            self.walked.add(walked[0])
        else:
            name = place[1] if isinstance(place[1], str) else access_name(place[1])
            self.closed.add(str(name))

    def _passes(self, root: Expression) -> frozenset[Pass]:
        """The walk keys a part names, each part read once however often the path shares it."""
        if not isinstance(root, list):
            return _NONE
        below = self._below
        stack: list[tuple[list[Expression], bool]] = [(root, False)]
        while stack:
            node, ready = stack.pop()
            if id(node) in below:
                continue
            walked = walk_key(node)
            if walked is not None:
                below[id(node)] = frozenset({walked})
            elif not ready:
                stack.append((node, True))
                stack.extend((part, False) for part in node[1:] if isinstance(part, list))
            else:
                parts = [below[id(part)] for part in node[1:] if isinstance(part, list)]
                below[id(node)] = frozenset().union(*parts) if parts else _NONE
        return below[id(root)]

    def chosen(self) -> set[Pass]:
        """The passes the ask with chosen keys leaves to the solver: each a fork names, of a
        dict of the input of at most ``MOST_KEYS`` keys whose path keeps no other place, that no
        fact keeps at the input's key."""
        small = {name for name, shape in self.dicts.items() if len(shape.keys) <= MOST_KEYS}
        return {
            walked
            for walked in self.forked - self.pinned
            if walked[0] not in self.closed and walked[0] in small
        }

    def unnamed(self, prefix: tuple[Branch | Fact, ...]) -> tuple[Branch | Fact, ...]:
        """The path without each step whose check names a walk key, and without places: what
        holds on every walk, whichever keys it reads."""
        kept = (step for step in prefix if not self._passes(step.expression))
        return tuple(replace(step, place=None) if isinstance(step, Fact) else step for step in kept)

    def unread(self, prefix: tuple[Branch | Fact, ...]) -> tuple[Branch | Fact, ...]:
        """The path without each fact that a walk key's dict holds it: the walk read the key, so
        the fact is a place, which the ask without places leaves out."""
        return tuple(step for step in prefix if not _read_by_its_walk(step))

    def fixed(self, prefix: tuple[Branch | Fact, ...]) -> tuple[Branch | Fact, ...]:
        """The path with each walk key written as the key the input holds at its pass. A pass
        whose key a step names keeps that key at its place whatever a fork reads there, a given
        place: a fork that compares the key reads no value, and would read another key there."""
        if not self.walked:
            return prefix
        return _written(tuple(self._given(step) for step in prefix), self.written_key)

    def _given(self, step: Branch | Fact) -> Branch | Fact:
        """A walk's place at a pass whose key a step names, as a given place."""
        if not isinstance(step, Fact):
            return step
        place = step.place
        if not (isinstance(place, list) and len(place) == 3 and place[0] == "walked"):
            return step
        walked = walk_key(place[2])
        return replace(step, place=["given", place]) if walked in self.named else step

    def opened(
        self, prefix: tuple[Branch | Fact, ...]
    ) -> tuple[tuple[Branch | Fact, ...], dict[str, type], dict[str, object], dict[str, Order]]:
        """The path for the ask with chosen keys: each chosen walk key a leaf, every other the
        input's key, and the places of each dict with a chosen key left out, since its order
        keeps them; with each leaf's type and input value, and each such dict's order."""
        chosen = self.chosen()
        values = {leaf(walked): self.input_key(walked) for walked in chosen}
        leaves = {name: type(key) for name, key in values.items()}
        orders = {name: self._order(name, chosen) for name, _ in chosen}

        def swap(walked: Pass) -> Expression:
            return leaf(walked) if walked in chosen else self.written_key(walked)

        kept = [_unplaced(step, orders) for step in _written(prefix, swap)]
        return tuple(step for step in kept if step is not None), leaves, values, orders

    def _order(self, name: str, chosen: set[Pass]) -> Order:
        """A dict's walk up to the last pass its path names: each chosen pass by its leaf, and
        each other by the input's key there."""
        last = max(at for dict_name, at in self.named if dict_name == name)
        passes = [(name, at) for at in range(last + 1)]
        return tuple(
            (leaf(walked) if walked in chosen else None, self.input_key(walked))
            for walked in passes
        )

    def input_key(self, walked: Pass) -> object:
        """The key the input holds at a pass."""
        name, at = walked
        shape = self.dicts.get(name)
        if shape is None or not 0 <= at < len(shape.keys):
            raise UnwrittenError(f"no key at pass {at} of {name}")
        return shape.keys[at]

    def written_key(self, walked: Pass) -> Expression:
        """The key the input holds at a pass, as a fork writes it."""
        return key_term(self.input_key(walked), written=True)


def _read_by_its_walk(step: Branch | Fact) -> bool:
    """Whether a step is the fact that a walk key's own dict holds it: `["in", key, A]`."""
    expression = step.expression
    if not isinstance(step, Fact) or not isinstance(expression, list) or len(expression) != 3:
        return False
    walked = walk_key(expression[1])
    holder = expression[2]
    name = holder if isinstance(holder, str) else access_name(holder)
    return expression[0] == "in" and walked is not None and walked[0] == name


def _pins(fact: Fact) -> bool:
    """Whether a fact keeps a walk key at the key the input holds there: `["==", key, k]`."""
    expression = fact.expression
    return (
        isinstance(expression, list)
        and len(expression) == 3
        and expression[0] == "=="
        and fact.taken
        and walk_key(expression[1]) is not None
        and not isinstance(expression[2], list)
    )


def _unplaced(step: Branch | Fact, orders: Mapping[str, Order]) -> Branch | Fact | None:
    """A step of the path for the ask with chosen keys: a walk's place in a dict with an order
    left out, since the order keeps it; a fact that is only that place, None."""
    if not isinstance(step, Fact) or not isinstance(step.place, list) or len(step.place) != 3:
        return step
    head, part, _ = step.place
    name = part if isinstance(part, str) else access_name(part)
    if head != "walked" or name not in orders:
        return step
    return None if step.expression is None else replace(step, place=None)


def _written(
    prefix: tuple[Branch | Fact, ...], swap: Callable[[Pass], Expression]
) -> tuple[Branch | Fact, ...]:
    """The path with each walk key swapped, each part rewritten once however often it is
    shared, and a part with no walk key in it kept as it is."""
    memo: dict[int, Expression] = {}
    steps: list[Branch | Fact] = []
    for step in prefix:
        expression = _rewritten(step.expression, swap, memo)
        if isinstance(step, Fact):
            place = _rewritten(step.place, swap, memo)
            steps.append(replace(step, expression=expression, place=place))
        else:
            steps.append(replace(step, expression=expression))
    return tuple(steps)


def _rewritten(
    root: Expression, swap: Callable[[Pass], Expression], memo: dict[int, Expression]
) -> Expression:
    """One part with each walk key in it swapped, on a stack of its own."""
    if not isinstance(root, list):
        return root
    stack: list[tuple[list[Expression], bool]] = [(root, False)]
    while stack:
        node, ready = stack.pop()
        if id(node) in memo:
            continue
        walked = walk_key(node)
        if walked is not None:
            memo[id(node)] = swap(walked)
        elif not ready:
            stack.append((node, True))
            stack.extend((part, False) for part in node[1:] if isinstance(part, list))
        else:
            parts = [memo[id(part)] if isinstance(part, list) else part for part in node]
            changed = any(new is not old for new, old in zip(parts, node, strict=True))
            memo[id(node)] = parts if changed else node
    return memo[id(root)]
