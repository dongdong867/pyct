"""The tracked lists a path names, written for cvc5.

Render hands a part here when it is a list or reads one: a list the seed names, a display
``["[,]", ...]``, ``+`` and ``*`` of lists, a slice, a list inside a list, an item
``["[]", items, p]`` and a length ``["len", items]``. A list is a piece of ``list_terms``; an
item is a read split at its pieces, and a length a sum. Each argument's list is declared as its
length, from 0 to 1,000,000 (answers-hold-at-most-a-million-items), and one array per kind of
item a read takes, an array of arrays for the lists inside it.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeGuard

from pyct.binding.shapes import ListShape
from pyct.core.branch import Expression
from pyct.solver.list_terms import TRUE, Joined, Lin, Piece, Shown, Stored, Window, read

# the longest list an answer holds
MOST_ITEMS = 1_000_000

# the sort of the items of each kind a read takes, and the type render gives such a read
ITEM_SORTS: Mapping[str, str] = {"int": "Int", "str": "String"}
ITEM_TYPES: Mapping[str, type] = {"int": int, "str": str}

# the kind of an item render typed, as a list's items count kinds
_KIND_OF_TYPE: Mapping[type, str] = {
    int: "int",
    str: "str",
    bool: "bool",
    float: "float",
    list: "list",
    type(None): "none",
}

# a part's type as render reads it, None when nothing says
type TypeOf = Callable[[Expression], type | None]

# the heads that build a list from lists, or read one
_LIST_HEADS = frozenset({"[]", "len", "[,]", "+", "*", "[:]"})


class TrackedList:
    """The type render gives a part that is a tracked list: a list no single term holds."""


@dataclass(frozen=True)
class Kinds:
    """What a list's items can be: the kinds core counts, and with them those the solver may
    add. ``shape`` is the input's own shape for an argument's list or a list inside one, which
    types a read at a position from the start by that position alone."""

    kinds: frozenset[str]
    every: frozenset[str]
    shape: ListShape | None = None


def of_shape(shape: ListShape) -> Kinds:
    """What the items of a list of the input can be."""
    kinds = frozenset(shape.kinds)
    return Kinds(kinds, kinds | {shape.fill}, shape)


def _from_start(position: Expression) -> TypeGuard[int]:
    """Whether a position is a plain number from the start: the one a static read is typed by."""
    return isinstance(position, int) and not isinstance(position, bool) and position >= 0


def _access(part: Expression) -> str | None:
    """The name of an access to a list inside an argument, as the seed names it."""
    step = part
    while isinstance(step, list) and len(step) == 3 and step[0] == "[]":
        if isinstance(step[2], list):
            return None
        step = step[1]
    if step is part or not isinstance(step, str):
        return None
    return json.dumps(part)


class ListTerms:
    """The lists of one path: their kinds while render types the parts, their pieces while it
    writes them, and what they declare.

    ``named`` gives the written term of a part a piece reads, a leaf's constant or a defined
    part's name, as often as it is read; ``type_of`` is render's type of a part.
    ``definitions`` is render's own list, so a term defined here comes before any that reads
    it.
    """

    def __init__(self, shapes: Mapping[str, ListShape], symbols: Mapping[str, str]) -> None:
        self.shapes = shapes
        self.symbols = symbols
        self.named: Callable[[Expression], str] = str
        self.type_of: TypeOf = lambda part: None
        self.definitions: list[str] = []
        self.kinds: dict[int, Kinds] = {}
        self.named_kinds: dict[str, Kinds] = {}
        self.pieces: dict[int, Piece] = {}
        # each list part the path builds, in the order render made its piece
        self.built: list[list[Expression]] = []
        self.stored: dict[int, tuple[str, tuple[int, ...]]] = {}
        self.declared: dict[str, str] = {}
        self.bounded: dict[str, None] = {}
        self.guards: list[str] = []
        # the least length each list the seed names has on the path, by its length's term
        self.present: dict[str, int] = {}
        self.nonnegative: set[str] = set()
        # each term a position or a bound defined, by its text, and the name it has
        self.written: dict[str, str] = {}
        # each read of an item: the list part it reads and the position part, for the answer
        self.reads: list[tuple[Expression, Expression]] = []
        # each part a position or a bound reads, whose value the answer needs
        self.positions: dict[int, Expression] = {}

    def leaf(self, part: Expression) -> str | None:
        """The name of the list the seed names, when a part is one."""
        name = part if isinstance(part, str) else _access(part)
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
        if head == "[,]":
            return True
        return head in _LIST_HEADS and any(self.kinds_of(part) is not None for part in node[1:3])

    def result(self, node: list[Expression]) -> type | None:
        """The type of a part that builds or reads a list, noting a list's kinds.

        A list is a `TrackedList`, its length an int, and a read what it hands out.
        """
        head, *operands = node
        if head == "[,]":
            kinds = frozenset(self._item_kind(part) for part in operands)
            self.kinds[id(node)] = Kinds(kinds, kinds)
            return TrackedList
        lists = [kinds for part in operands if (kinds := self.kinds_of(part)) is not None]
        if head == "[]":
            return self._item_type(node, lists[0])
        if head == "len":
            return int
        self.kinds[id(node)] = Kinds(
            frozenset().union(*(kinds.kinds for kinds in lists)),
            frozenset().union(*(kinds.every for kinds in lists)),
        )
        return TrackedList

    def _item_type(self, node: list[Expression], kinds: Kinds) -> type | None:
        """What a read hands out: a list inside a list, or an int or a str."""
        position = node[2]
        if kinds.shape is not None and _from_start(position):
            kind = kinds.shape.kind_at(position)
            if kind == "list":
                row = kinds.shape.row_at(position) or ListShape(())
                self.kinds[id(node)] = of_shape(row)
                return TrackedList
            return ITEM_TYPES.get(kind)
        tracked = [ITEM_TYPES[kind] for kind in kinds.kinds if kind in ITEM_TYPES]
        return tracked[0] if len(tracked) == 1 else None

    def _item_kind(self, part: Expression) -> str:
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

    def piece(self, part: Expression) -> Piece:
        """The piece a list part is."""
        name = self.leaf(part)
        if name is not None:
            return self._stored(name, (), self.shapes[name])
        return self.pieces[id(part)]

    def build(self, node: list[Expression]) -> None:
        """Make the piece a list part is, its own list parts already made."""
        head, *operands = node
        kinds = self.kinds[id(node)]
        if head == "[]":
            piece: Piece = self._row(node, kinds)
        elif head == "[,]":
            items = [(self._item_term(part), self._item_kind(part)) for part in operands]
            piece = Shown(Lin(len(items)), kinds.kinds, kinds.every, items=items)
        elif head == "[:]":
            piece = self._window(operands, kinds)
        else:
            piece = self._joined(str(head), operands, kinds)
        self.pieces[id(node)] = piece
        self.built.append(node)

    def scalar(self, node: list[Expression], kind: type | None) -> str:
        """The term of a list's length, or of an item of ``kind`` read from one."""
        head, operand, *rest = node
        piece = self.piece(operand)
        if head == "len":
            return piece.length.text()
        item = next((name for name, python in ITEM_TYPES.items() if python is kind), None)
        if item is None:
            # a read of an item no term holds, a None or a list inside say, which a sort's
            # display writes: no fork reads it, so it has no term
            return ""
        position = self._position(rest[0], piece)
        found = read(piece, position, item, self.nonnegative)
        if found.value is None:
            raise ValueError(f"pyct cannot render {head}: no {kind} item is read there")
        if found.guard != TRUE:
            self.guards.append(found.guard)
        if isinstance(piece, Stored):
            self._present(piece.length, rest[0])
        self.reads.append((operand, rest[0]))
        return found.value

    def _present(self, length: Lin, position: Expression) -> None:
        """Note that a list the seed names holds the item a fork read at a plain position.

        The target read it, so every input on the path has it: a fork on an item Python's own
        code compared, in `list.index` with a start say, has no long-enough fork before it.
        """
        if isinstance(position, int) and not isinstance(position, bool):
            needed = position + 1 if position >= 0 else -position
            term = length.text()
            self.present[term] = max(self.present.get(term, 0), needed)

    def _item_term(self, part: Expression) -> str | None:
        """An item's term, for an item a read can hand out: an int or a str."""
        return self.named(part) if self._item_kind(part) in ITEM_SORTS else None

    def _stored(self, name: str, positions: tuple[int, ...], shape: ListShape) -> Stored:
        """An argument's list, or a list inside one at ``positions``: its length and arrays."""
        symbol = self.symbols[name]
        length = self._declared(symbol, positions, "len")
        if length not in self.bounded:
            self.bounded[length] = None
            self.nonnegative.add(length)
        kinds = of_shape(shape) if positions else self.kinds_of(name)
        assert kinds is not None
        return Stored(
            Lin.of(length),
            kinds.kinds,
            kinds.every,
            arrays=lambda kind: self._declared(symbol, positions, kind),
            shape=shape,
        )

    def _declared(self, symbol: str, positions: tuple[int, ...], part: str) -> str:
        """One array or length of a list, declared the first time a term reads it, and read at
        the positions that reach a list inside.

        The length of a list the seed names is an ``Int``; the lengths of the lists inside it,
        and the items of each kind, are arrays over their positions, one level per list.
        """
        depth = len(positions) + (0 if part == "len" else 1)
        levels = "rows." * len(positions)
        name = f"|{symbol}.{levels}{part}|"
        sort = "Int" if part == "len" else ITEM_SORTS[part]
        for _ in range(depth):
            sort = f"(Array Int {sort})"
        self.declared.setdefault(name, sort)
        term = name
        for at in positions:
            term = f"(select {term} {at})"
        return term

    def _row(self, node: list[Expression], kinds: Kinds) -> Stored:
        """A list inside a list the seed names, at a position from the start."""
        outer, at = node[1], node[2]
        if not _from_start(at):
            raise ValueError(
                f"pyct cannot render a list inside a list at {at}: core reads one only at its place"
            )
        name = self.leaf(outer)
        where = (name, ()) if name is not None else self.stored[id(outer)]
        self._present(self.piece(outer).length, at)
        positions = (*where[1], at)
        self.stored[id(node)] = (where[0], positions)
        return self._stored(where[0], positions, kinds.shape or ListShape(()))

    def _joined(self, head: str, operands: list[Expression], kinds: Kinds) -> Joined:
        """Lists joined by `+`, or one repeated by `*` a plain number of times. A read runs
        the joins flat (see ``Joined.flat``), so a list appended to thousands of times costs
        one part a join here."""
        if head == "+":
            left, right = (self.piece(operand) for operand in operands)
            return Joined(left.length.plus(right.length), kinds.kinds, kinds.every, [left, right])
        times = max(next(part for part in operands if isinstance(part, int)), 0)
        listed = self.piece(next(part for part in operands if not isinstance(part, int)))
        return Joined(listed.length.times(times), kinds.kinds, kinds.every, [listed] * times)

    def _window(self, operands: list[Expression], kinds: Kinds) -> Window:
        """A slice, clamped to the list as Python clamps it; a step of -1 runs back from its
        start."""
        base = self.piece(operands[0])
        size = base.length
        bounds = [self._bound(part) for part in operands[1:3]]
        if len(operands) > 3 and operands[3] == -1:
            start = self._back(bounds[0], size, size.minus(Lin(1)))
            stop = self._back(bounds[1], size, Lin(-1))
            length, step = self._nonnegative(start.minus(stop)), -1
        else:
            start = self._clamped(bounds[0], size, Lin())
            stop = self._clamped(bounds[1], size, size)
            length = (
                size.minus(start) if bounds[1] is None else self._nonnegative(stop.minus(start))
            )
            step = 1
        return Window(length, kinds.kinds, kinds.every, base=base, start=start, step=step)

    def _bound(self, part: Expression) -> Lin | None:
        """A slice bound or a position as a term: a number, None for a missing bound, or a
        tracked int's term, whose value the answer reads."""
        if part is None:
            return None
        if type(part) is int:
            return Lin(part)
        self.positions[id(part)] = part
        return Lin.of(self.named(part))

    def _clamped(self, bound: Lin | None, size: Lin, missing: Lin) -> Lin:
        """A bound of a step-1 slice as Python clamps it: counted back from the end when
        negative, then kept between 0 and the length."""
        if bound is None:
            return missing
        if bound.number() == 0:
            return Lin()
        value, length = bound.text(), size.text()
        counted = f"(ite (< (+ {value} {length}) 0) 0 (+ {value} {length}))"
        clamped = f"(ite (< {value} 0) {counted} (ite (> {value} {length}) {length} {value}))"
        return self._defined(clamped, nonnegative=True)

    def _back(self, bound: Lin | None, size: Lin, missing: Lin) -> Lin:
        """A bound of a step -1 slice as Python clamps it: counted back from the end when
        negative, -1 when that is still before the start, and the last position past the end."""
        if bound is None:
            return missing
        value, length = bound.text(), size.text()
        counted = f"(ite (< (+ {value} {length}) 0) (- 1) (+ {value} {length}))"
        clamped = (
            f"(ite (< {value} 0) {counted} (ite (>= {value} {length}) (- {length} 1) {value}))"
        )
        return self._defined(clamped, nonnegative=False)

    def _nonnegative(self, difference: Lin) -> Lin:
        """``max(0, difference)``: a slice's length from its clamped bounds."""
        least = difference.lowest(self.nonnegative)
        if least is not None and least >= 0:
            return difference
        text = difference.text()
        return self._defined(f"(ite (< {text} 0) 0 {text})", nonnegative=True)

    def _position(self, part: Expression, piece: Piece) -> Lin:
        """The position an item is read at: from the start, back from the end for a negative
        number, and a tracked index counted back from the end when it is negative."""
        bound = self._bound(part)
        assert bound is not None
        number = bound.number()
        if number is not None:
            return bound if number >= 0 else piece.length.plus(bound)
        value, length = bound.text(), piece.length.text()
        return self._defined(f"(ite (< {value} 0) (+ {value} {length}) {value})", nonnegative=False)

    def _defined(self, text: str, *, nonnegative: bool) -> Lin:
        """A term written once, as ``(define-fun p!N () Int ...)``, and named wherever read.

        Slices with the same bounds on one list clamp them the same way, so a term already
        written is named again rather than defined twice.
        """
        if text not in self.written:
            name = f"p!{len(self.definitions)}"
            self.definitions.append(f"(define-fun {name} () Int {text})")
            self.written[text] = name
            if nonnegative:
                self.nonnegative.add(name)
        return Lin.of(self.written[text])

    def asked(self) -> list[str]:
        """What the program asks cvc5 for about the lists: each length and array it declared,
        and each position's term the answer reads (see ``list_answers``)."""
        names = list(self.declared)
        names += [
            term
            for part in self.positions.values()
            if not (term := self.named(part)).startswith("|")
        ]
        return names

    def answered(self) -> set[str]:
        """The names the answer holds for the lists, as cvc5 writes them back: without bars."""
        return {name.strip("|") for name in self.asked()}

    def assertions(self) -> list[str]:
        """What the program asserts of the lists: each length at most a million, not negative,
        and each read's guard."""
        lengths = [f"(assert (<= 0 {length} {MOST_ITEMS}))" for length in self.bounded]
        held = [f"(assert (>= {length} {least}))" for length, least in self.present.items()]
        return lengths + held + [f"(assert {guard})" for guard in self.guards]
