"""What a tracked list's parts are, as render types a path: lists, their lengths, and the items
read from them.

A list is a `TrackedList`, which no single term holds. A read of a list that can hold a float or
a bool says the kind Python read (``core.branch.READ_HEADS``), since Python compares an int with
a float and a path cannot say. Any other item read from a list is an int or a str: by its
position, when the position is from the start of a list the input holds; by the list, when every
item it can hold is of one kind; and else by what the path does with it, since Python compares and
adds only values of one kind, and the fork was recorded on a value of the kind the target read.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, MutableMapping
from dataclasses import dataclass
from typing import TypeGuard

from pyct.binding.shapes import ListShape
from pyct.core.foundation.branch import ACCESS_STEPS, READ_HEADS, Expression
from pyct.core.strs.str_splits import LISTED_SPLITS
from pyct.solver.words import WORD_EDGES

# the sort of the items of each kind a read takes, and the type render gives such a read
ITEM_SORTS: Mapping[str, str] = {"int": "Int", "str": "String", "float": "Float64", "bool": "Bool"}
ITEM_TYPES: Mapping[str, type] = {"int": int, "str": str, "float": float, "bool": bool}

# the kind each read head says, and the kinds a read may take in place of the one Python read
READ_KINDS: Mapping[str, str] = {head: kind for kind, head in READ_HEADS.items()}
_NUMBERS = frozenset({"int", "float", "bool"})

# the kind of an item render typed, as a list's items count kinds
_KIND_OF_TYPE: Mapping[type, str] = {
    int: "int",
    str: "str",
    bool: "bool",
    float: "float",
    list: "list",
    type(None): "none",
}

# the heads whose first operand is a str, whatever the rest are
_ON_A_STR = frozenset(
    {
        "startswith",
        "endswith",
        "find",
        "rfind",
        "index",
        "rindex",
        "count",
        "replace",
        "removeprefix",
        "removesuffix",
        *WORD_EDGES,
        "[]",
        "[:]",
        "len",
    }
)

# a part's type as render reads it, None when nothing says
type TypeOf = Callable[[Expression], type | None]

# the heads that build a list from lists, or read one
_LIST_HEADS = frozenset({"[]", "len", "[,]", "+", "*", "[:]", *READ_KINDS})

# the splits whose list is tracked, each a list of strs; `partition` hands back a tuple
SPLIT_HEADS = LISTED_SPLITS


class TrackedList:
    """The type render gives a part that is a tracked list: a list no single term holds."""


@dataclass(frozen=True)
class Kinds:
    """What a list's items can be: the kinds core counts, and with them those the solver may
    add. ``shape`` is the input's own shape for an argument's list or a list inside one at a
    place, which types a read at a position from the start by that position alone. ``longest``
    is the most items any of the input's lists it may be holds, for a row read where no shape
    says which: what its length's first hold starts from (``size_holds``)."""

    kinds: frozenset[str]
    every: frozenset[str]
    shape: ListShape | None = None
    longest: int = 0


# what a split's pieces are: strs, and only strs
_PIECES = Kinds(frozenset({"str"}), frozenset({"str"}))


def of_shape(shape: ListShape) -> Kinds:
    """What the items of a list of the input can be."""
    kinds = frozenset(shape.kinds)
    return Kinds(kinds, kinds | {shape.fill}, shape)


def of_rows(shape: ListShape) -> Kinds:
    """What the items of any list inside a list of the input can be: each row's, and an added
    row's."""
    rows = [*shape.rows.values(), *([shape.fill_row] if shape.fill_row is not None else [])]
    kinds = frozenset().union(*(row.kinds for row in rows))
    every = frozenset().union(*(of_shape(row).every for row in rows))
    longest = max((len(row.kinds) for row in rows), default=0)
    return Kinds(frozenset(kinds), every, longest=longest)


def measured(part: Expression) -> Expression | None:
    """The part a length measures, ``items`` for ``["len", items]``; None for any other part."""
    if isinstance(part, list) and len(part) == 2 and part[0] == "len":
        return part[1]
    return None


def from_start(position: Expression) -> TypeGuard[int]:
    """Whether a position is a plain number from the start: the one a static read is typed by."""
    return isinstance(position, int) and not isinstance(position, bool) and position >= 0


def access(part: Expression) -> str | None:
    """The name of an access to a list inside an argument, as the seed names it."""
    step = part
    while isinstance(step, list) and len(step) == 3 and _is_a_step(step[0]):
        if isinstance(step[2], list):
            return None
        step = step[1]
    if step is part or not isinstance(step, str):
        return None
    return json.dumps(part)


def _is_a_step(head: Expression) -> bool:
    """Whether a head is one an access takes on its way in from a parameter."""
    return isinstance(head, str) and head in ACCESS_STEPS


def _identity(part: Expression) -> object:
    """What tells a part of a read from another: a list by the object it is, as a path holds one
    read's list and one read's index, and anything else by its value."""
    return id(part) if isinstance(part, list) else part


class ListTyping:
    """The kinds of the lists of one path, while render types its parts.

    ``type_of`` is render's type of a part. ``row_shapes`` holds, for a list inside a list read
    at a position not from the start, the shape of the list it is inside.
    """

    def __init__(self, shapes: Mapping[str, ListShape]) -> None:
        self.shapes = shapes
        self.type_of: TypeOf = lambda part: None
        self.kinds: dict[int, Kinds] = {}
        self.named_kinds: dict[str, Kinds] = {}
        self.row_shapes: dict[int, ListShape] = {}
        # each read whose kind neither its position nor its list says, typed by the path
        self.untyped: set[int] = set()
        # each read that may land on another kind than Python read: the kinds an ask can write
        # for it, by its place among them (``read_kinds``), the kind each ask gives it, and
        # whether one may land on a kind no ask can write
        self.moving: dict[tuple[object, object], int] = {}
        self.other_kinds: list[frozenset[str]] = []
        self.chosen: Mapping[int, str] = {}
        self.untried = False

    def leaf(self, part: Expression) -> str | None:
        """The name of the list the seed names, when a part is one."""
        name = part if isinstance(part, str) else access(part)
        return name if name is not None and name in self.shapes else None

    def kinds_of(self, part: Expression) -> Kinds | None:
        """What a list part's items can be, or None for a part that is not a list."""
        name = self.leaf(part)
        if name is None:
            return self.kinds.get(id(part)) if isinstance(part, list) else None
        # a shape is read for every part that names its list, so each is worked out once
        if name not in self.named_kinds:
            self.named_kinds[name] = of_shape(self.shapes[name])
        return self.named_kinds[name]

    def involves(self, node: list[Expression]) -> bool:
        """Whether a part builds a list or reads one: a display, or a list head on a list."""
        head = node[0]
        if head in ("[,]", "pin") or head in SPLIT_HEADS:
            return True
        return head in _LIST_HEADS and any(self.kinds_of(part) is not None for part in node[1:3])

    def result(self, node: list[Expression]) -> type | None:
        """The type of a part that builds or reads a list, noting a list's kinds.

        A list is a `TrackedList`, its length an int, and a read what it hands out.
        """
        head, *operands = node
        if head == "[,]":
            kinds = frozenset(self.item_kind(part) for part in operands)
            self.kinds[id(node)] = Kinds(kinds, kinds)
            return TrackedList
        if head in SPLIT_HEADS:
            self.kinds[id(node)] = _PIECES
            return TrackedList
        lists = [kinds for part in operands if (kinds := self.kinds_of(part)) is not None]
        if head == "pin":
            return int
        if head == "[]":
            return self._item_type(node, lists[0])
        if head in READ_KINDS:
            return self._said_type(node, lists[0])
        if head == "len":
            return int
        self.kinds[id(node)] = Kinds(
            frozenset().union(*(kinds.kinds for kinds in lists)),
            frozenset().union(*(kinds.every for kinds in lists)),
        )
        return TrackedList

    def _item_type(self, node: list[Expression], kinds: Kinds) -> type | None:
        """What a read that says no kind hands out: a list inside a list, or an int or a str."""
        position = node[2]
        if kinds.shape is not None and from_start(position):
            kind = kinds.shape.kind_at(position)
            if kind == "list":
                row = kinds.shape.row_at(position) or ListShape(())
                self.kinds[id(node)] = of_shape(row)
                return TrackedList
            return ITEM_TYPES.get(kind)
        if kinds.every == {"list"} and kinds.shape is not None:
            self.kinds[id(node)] = of_rows(kinds.shape)
            self.row_shapes[id(node)] = kinds.shape
            return TrackedList
        tracked = [ITEM_TYPES[kind] for kind in kinds.every if kind in ITEM_TYPES]
        if len(tracked) == 1:
            return tracked[0]
        self.untyped.add(id(node))
        return None

    def _said_type(self, node: list[Expression], kinds: Kinds) -> type:
        """What a read that says its kind hands out: that kind, or the kind this ask gives it.
        A position from the start of a list the input holds, or of a display, always lands on
        the same item, and an answer keeps its kind."""
        seen = READ_KINDS[str(node[0])]
        position = node[2]
        fixed = kinds.shape is not None or (isinstance(node[1], list) and node[1][0] == "[,]")
        if fixed and from_start(position):
            return ITEM_TYPES[seen]
        if seen not in _NUMBERS:
            self.untried |= bool(kinds.every - {seen})
            return ITEM_TYPES[seen]
        self.untried |= bool(kinds.every - _NUMBERS)
        others = (kinds.every & _NUMBERS) - {seen}
        if not others:
            return ITEM_TYPES[seen]
        read = (_identity(node[1]), _identity(position))
        if read not in self.moving:
            self.moving[read] = len(self.other_kinds)
            self.other_kinds.append(others)
        return ITEM_TYPES[self.chosen.get(self.moving[read], seen)]

    def infer(self, node: list[Expression], types: MutableMapping[int, type | None]) -> None:
        """Type each read in a part that neither its position nor its list types, by the part:
        the other operand's type, or a str where the part reads its operand as one."""
        head, *operands = node
        for at, part in enumerate(operands):
            if not isinstance(part, list) or id(part) not in self.untyped or types.get(id(part)):
                continue
            if head in _ON_A_STR and at == 0:
                types[id(part)] = str
                continue
            others = [self.type_of(other) for other in operands if other is not part]
            types[id(part)] = next((kind for kind in others if kind in (int, str)), None)

    def item_kind(self, part: Expression) -> str:
        """The kind of an item a display holds: a literal's own, a list's, or the type render
        gave it."""
        if isinstance(part, str) and part.startswith(("'", '"')):
            return "str"
        if not isinstance(part, list | str):
            return _KIND_OF_TYPE.get(type(part), "other")
        if self.kinds_of(part) is not None:
            return "list"
        typed = self.type_of(part)
        return "other" if typed is None else _KIND_OF_TYPE.get(typed, "other")

    def listed(self, order: list[list[Expression]]) -> set[int]:
        """The parts of a path that are lists, found by typing it: what a string's join must
        leave alone."""
        for node in order:
            if self.involves(node):
                self.result(node)
        return set(self.kinds)

    def operands(self, node: list[Expression]) -> list[Expression]:
        """The parts a list part reads that its pieces read more than once: each is defined."""
        return [part for part in node[1:] if isinstance(part, list) and self.kinds_of(part) is None]
