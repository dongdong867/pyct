"""The tracked lists a path names, written for cvc5.

Render hands a part here when it is a list or reads one: a list the seed names, a display
``["[,]", ...]``, ``+`` and ``*`` of lists, a slice, a list inside a list, an item
``["[]", items, p]`` and a length ``["len", items]``. A list is a piece of ``list_terms``; an
item is a read split at its pieces (``list_reader``), and a length a sum. Each argument's list
is declared as its length, from 0 to 1,000,000 (answers-hold-at-most-a-million-items), and one
array per kind of item a read takes, an array of arrays for the lists inside it.

The path's own forks on a list's length say how long it is at least, `len(items) > 0` say, and
a slice clamped to a list at least that long is its bound as written: so a list changed in place
at a plain index, `counts[0] += 1` thirty times, is a row of pieces a read goes through once.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from pyct.binding.shapes import ListShape
from pyct.core.branch import Branch, Expression
from pyct.solver.list_kinds import ITEM_SORTS, ITEM_TYPES, Kinds, ListTyping, TrackedList
from pyct.solver.list_reader import Context, Memo, read
from pyct.solver.list_slices import Slices
from pyct.solver.list_terms import (
    FALSE,
    TRUE,
    Guard,
    Joined,
    Least,
    Lin,
    Piece,
    Repeated,
    Shown,
    Stored,
    both,
    compare,
    either,
    equal,
    shape_guard,
)

__all__ = ["ITEM_SORTS", "ListTerms", "TrackedList", "UnencodedError"]

# the longest list an answer holds, and the longest a list the target builds from one
MOST_ITEMS = 1_000_000

# how each fork on a list's length, taken or not, says how long the list is at least: by the
# number it compares with
_AT_LEAST: Mapping[tuple[str, bool], Callable[[int], int]] = {
    (">", True): lambda number: number + 1,
    (">=", True): lambda number: number,
    ("==", True): lambda number: number,
    ("<", False): lambda number: number,
    ("<=", False): lambda number: number + 1,
    ("!=", True): lambda number: 1 if number == 0 else 0,
}

# where a list inside a list sits: the list the seed names, each position on the way as the
# path wrote it, and each as a term
type Place = tuple[str, tuple[Expression, ...], tuple[str, ...]]


class UnencodedError(ValueError):
    """A read on the path that no term writes: its kind is one nothing on the path tells."""


class ListTerms(ListTyping, Slices):
    """The lists of one path: their kinds while render types the parts, their pieces while it
    writes them, and what they declare.

    ``named`` gives the written term of a part a piece reads, a leaf's constant or a defined
    part's name, as often as it is read. ``definitions`` is render's own list, so a term
    defined here comes before any that reads it. ``until`` is the instant writing must end by.
    """

    def __init__(self, shapes: Mapping[str, ListShape], symbols: Mapping[str, str]) -> None:
        ListTyping.__init__(self, shapes)
        Slices.__init__(self)
        self.symbols = symbols
        self.until: float | None = None
        self.pieces: dict[int, Piece] = {}
        self.leaves: dict[str, Stored] = {}
        # each list part the path builds, in the order render made its piece
        self.built: list[list[Expression]] = []
        self.stored: dict[int, Place] = {}
        self.declared: dict[str, str] = {}
        self.bounded: dict[str, None] = {}
        self.capped: list[str] = []
        self.guards: list[str] = []
        # the least length each list the seed names has on the path, by its length's term
        self.present: dict[str, int] = {}
        # how long each list part is at least on the path, by the path's forks on it
        self.facts: dict[int, int] = {}
        self.memo: Memo = {}
        # each read of an item: the list part it reads and the position part, for the answer
        self.reads: list[tuple[Expression, Expression]] = []

    def learn(self, prefix: tuple[Branch, ...]) -> None:
        """Note how long each list is at least, by the forks on its length the path takes."""
        for fork in prefix:
            expression = fork.expression
            if not (isinstance(expression, list) and len(expression) == 3):
                continue
            op, measured, number = expression
            least = _AT_LEAST.get((str(op), fork.taken))
            if least is None or type(number) is not int:
                continue
            if isinstance(measured, list) and len(measured) == 2 and measured[0] == "len":
                self._fact(measured[1], least(number))

    def _fact(self, part: Expression, least: int) -> None:
        name = self.leaf(part)
        if name is not None:
            length = self._declared(self.symbols[name], (), "len")
            self.least[length] = max(self.least.get(length, 0), least)
        elif isinstance(part, list):
            self.facts[id(part)] = max(self.facts.get(id(part), 0), least)

    def _apply_fact(self, node: list[Expression], piece: Piece) -> None:
        """A fork's bound on a list the path built, as a bound on the one term its length adds."""
        least = self.facts.get(id(node))
        atoms = piece.length.atoms
        if least is None or len(atoms) != 1 or atoms[0][1] != 1:
            return
        term, bound = atoms[0][0], least - piece.length.const
        self.least[term] = max(self.least.get(term, bound), bound)

    def piece(self, part: Expression) -> Piece:
        """The piece a list part is. A list the seed names is one piece however often it is
        read, so a read of it at one position is written once."""
        name = self.leaf(part)
        if name is None:
            return self.pieces[id(part)]
        if name not in self.leaves:
            kinds = self.kinds_of(name)
            assert kinds is not None
            self.leaves[name] = self._stored(name, (), kinds, shape_guard(self.shapes[name]))
        return self.leaves[name]

    def build(self, node: list[Expression]) -> None:
        """Make the piece a list part is, its own list parts already made."""
        head, *operands = node
        kinds = self.kinds[id(node)]
        if head == "[]":
            piece: Piece = self._row(node, kinds)
        elif head == "[,]":
            items = [(self._item_term(part), self.item_kind(part)) for part in operands]
            piece = Shown(Lin(len(items)), kinds.kinds, kinds.every, items=items)
        elif head == "[:]":
            piece = self.window(self.piece(operands[0]), operands[1:], kinds)
        elif head == "+":
            left, right = (self.piece(operand) for operand in operands)
            piece = Joined(left.length.plus(right.length), kinds.kinds, kinds.every, [left, right])
        else:
            piece = self._repeated(operands, kinds)
        self.pieces[id(node)] = piece
        self.built.append(node)
        self._apply_fact(node, piece)

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
        position = self.position(rest[0], piece)
        found = read(piece, position, item, self._context())
        if found.value is None:
            raise UnencodedError(f"pyct cannot render {head}: no {kind} item is read there")
        if found.guard != TRUE:
            self.guards.append(found.guard)
        if isinstance(piece, Stored):
            self._present(piece.length, rest[0])
        self.reads.append((operand, rest[0]))
        return found.value

    def _context(self) -> Context:
        return Context(self.least, self.memo, self._define_read, ITEM_SORTS, self.until)

    def _define_read(self, text: str, sort: str) -> str:
        """A read written once, as ``(define-fun r!N () Sort ...)``, and named wherever read."""
        key = f"{sort} {text}"
        if key not in self.written:
            name = f"r!{len(self.definitions)}"
            self.definitions.append(f"(define-fun {name} () {sort} {text})")
            self.written[key] = name
        return self.written[key]

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
        return self.named(part) if self.item_kind(part) in ITEM_SORTS else None

    def _stored(self, name: str, positions: tuple[str, ...], kinds: Kinds, guard: Guard) -> Stored:
        """An argument's list, or a list inside one at ``positions``: its length and arrays."""
        symbol = self.symbols[name]
        length = self._declared(symbol, positions, "len")
        if length not in self.bounded:
            self.bounded[length] = None
            self.least[length] = max(self.least.get(length, 0), 0)
        return Stored(
            Lin.of(length),
            kinds.kinds,
            kinds.every,
            arrays=lambda kind: self._declared(symbol, positions, kind),
            guard=guard,
        )

    def _declared(self, symbol: str, positions: tuple[str, ...], part: str) -> str:
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
        """A list inside a list the seed names, at a position from the start, from the end, or
        at a tracked index: the arrays of the lists inside, read at that position."""
        outer, at = node[1], node[2]
        name = self.leaf(outer)
        root, places, texts = (name, (), ()) if name is not None else self.stored[id(outer)]
        outer_piece = self.piece(outer)
        self._present(outer_piece.length, at)
        position = self.position(at, outer_piece)
        self.stored[id(node)] = (root, (*places, at), (*texts, position.text()))
        guard = self._row_guard(node, kinds, position)
        return self._stored(root, (*texts, position.text()), kinds, guard)

    def _row_guard(self, node: list[Expression], kinds: Kinds, position: Lin) -> Guard:
        """Where a list inside holds an item of a kind: its own shape at a place, and at a
        position the path computes, the shape of whichever list inside it lands on."""
        if kinds.shape is not None:
            return shape_guard(kinds.shape)
        outer = self.row_shapes[id(node)]
        rows = [(at, shape_guard(row)) for at, row in outer.rows.items()]
        added = None if outer.fill_row is None else shape_guard(outer.fill_row)

        def guard(at: Lin, kind: str, least: Least) -> str:
            found = FALSE
            for place, inner in rows:
                found = either(found, both(equal(position, place, least), inner(at, kind, least)))
            if added is not None:
                past = compare(Lin(len(outer.kinds)), position, least, or_equal=True)
                found = either(found, both(past, added(at, kind, least)))
            return found

        return guard

    def _repeated(self, operands: list[Expression], kinds: Kinds) -> Repeated:
        """A list repeated a plain number of times: one piece, and held, as an answer is, to a
        million items, so no answer makes the target build a list past that."""
        times = max(next(part for part in operands if isinstance(part, int)), 0)
        listed = self.piece(next(part for part in operands if not isinstance(part, int)))
        length = listed.length.times(times)
        if times > 1:
            self.capped.append(f"(assert (<= {length.text()} {MOST_ITEMS}))")
        return Repeated(length, kinds.kinds, kinds.every, base=listed)

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
        each list the target repeats no longer, and each read's guard."""
        lengths = [f"(assert (<= 0 {length} {MOST_ITEMS}))" for length in self.bounded]
        held = [f"(assert (>= {length} {least}))" for length, least in self.present.items()]
        return lengths + self.capped + held + [f"(assert {guard})" for guard in self.guards]
