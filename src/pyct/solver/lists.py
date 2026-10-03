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
from dataclasses import dataclass, field

from pyct.binding.shapes import DictShape, ListShape
from pyct.core.branch import Branch, Expression
from pyct.solver.answer_size import MOST_ITEMS, longest_string
from pyct.solver.list_kinds import (
    ITEM_SORTS,
    ITEM_TYPES,
    SPLIT_HEADS,
    Kinds,
    ListTyping,
    TrackedList,
    measured,
)
from pyct.solver.list_reader import Context, Memo, RenderTooLargeError, Shared, read
from pyct.solver.list_slices import Slices
from pyct.solver.list_terms import (
    FALSE,
    TRUE,
    Counted,
    Guard,
    Joined,
    Least,
    Lin,
    Piece,
    Read,
    Repeated,
    Shown,
    Stored,
    both,
    compare,
    either,
    equal,
    shape_guard,
    summed,
)
from pyct.solver.split_paths import Splits

__all__ = ["ITEM_SORTS", "ListTerms", "Origin", "TrackedList", "UnencodedError"]

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


# the steps one read takes before its program is written again with its clamps settled: far
# more than a read through a list changed at plain positions takes, and far less than one that
# doubles with each cut
READ_STEPS = 512


@dataclass(frozen=True)
class Origin:
    """The input whose path this is: each tracked list and dict with its shape, each leaf's
    value, and how the program is written for it.

    ``settle`` names the list parts whose clamps, where the path leaves them open, go the way
    they went there (see ``list_slices``), and ``everywhere`` settles every one. ``hold`` says
    whether a list the target repeats holds the answer's lengths (see ``_repeated``), and
    ``bounded`` whether each bound a form is exact inside is held (see ``render._bounded``).
    ``steps`` is the most steps one read takes before its program is written again settled,
    None for no limit; ``most`` the most all reads of the program take together before the
    program is given up (``ProgramTooLargeError``), None for no limit; and ``until`` the
    monotonic instant writing must end by. ``keep`` says whether each dict keeps the input's
    keys no fork names and makes none up, ``pinned`` whether it keeps each key a walk read at its
    place, and ``lookups`` the most steps a path's tracked-key lookups take together before the
    program is given up, None for no limit (see ``dicts``). ``places`` are the places the
    path's facts keep: which key a walk read where (see ``core.dict_reads.placed``).
    ``fixed_reads`` says whether a piece of a split read from its end, where no walk of the
    reversed string reads it, holds the string to the count c* (see ``split_lists``).
    """

    shapes: Mapping[str, ListShape] = field(default_factory=dict)
    dicts: Mapping[str, DictShape] = field(default_factory=dict)
    values: Mapping[str, object] = field(default_factory=dict)
    settle: frozenset[int] = frozenset()
    everywhere: bool = False
    hold: bool = True
    bounded: bool = True
    steps: int | None = READ_STEPS
    most: int | None = None
    until: float | None = None
    keep: bool = True
    pinned: bool = True
    lookups: int | None = None
    places: tuple[Expression, ...] = ()
    fixed_reads: bool = True


class UnencodedError(ValueError):
    """A read on the path that no term writes: its kind is one nothing on the path tells."""


class ListTerms(ListTyping, Slices):
    """The lists of one path: their kinds while render types the parts, their pieces while it
    writes them, and what they declare.

    ``named`` gives the written term of a part a piece reads, a leaf's constant or a defined
    part's name, as often as it is read. ``definitions`` is render's own list, so a term
    defined here comes before any that reads it. ``source`` is the input whose path this is (see
    ``start_from``), with the instant writing must end by.
    """

    def __init__(self, shapes: Mapping[str, ListShape], symbols: Mapping[str, str]) -> None:
        ListTyping.__init__(self, shapes)
        Slices.__init__(self)
        self.symbols = symbols
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
        # the input whose path this is, and how the program is written for it
        self.source = Origin()
        self.shared: Shared | None = None
        self.places: dict[int, int] = {}
        # each str item read, whose term is held to the most characters an answer holds
        self.strings: dict[str, None] = {}
        # each read of an item: the list part it reads and the position part, for the answer
        self.reads: list[tuple[Expression, Expression]] = []
        # the splits' lists the path reads
        self.splits = Splits()

    def learn(self, prefix: tuple[Branch, ...]) -> None:
        """Note how long each list is at least, by the forks on its length the path takes, and
        what the splits' lists learn of the path."""
        self.splits.learn(prefix)
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

    def length_of(self, part: Expression) -> Lin | None:
        listed = measured(part)
        if listed is not None and self.kinds_of(listed) is not None:
            return self.piece(listed).length
        return None

    def build(self, node: list[Expression]) -> None:
        """Make the piece a list part is, its own list parts already made."""
        head, *operands = node
        kinds = self.kinds[id(node)]
        if head == "[]":
            piece: Piece = self._row(node, kinds)
        elif head == "[,]":
            piece = self._shown(operands, kinds)
        elif head == "[:]":
            settle = self.source.everywhere or len(self.built) in self.source.settle
            piece = self.window(self.piece(operands[0]), operands[1:], kinds, settle=settle)
        elif head == "+":
            piece = self._joined(operands, kinds)
        elif head in SPLIT_HEADS:
            piece = self._split(node, kinds)
        else:
            piece = self._repeated(operands, kinds)
        self.pieces[id(node)] = piece
        # a part is known across the writings of one path by its place in the order it is built
        self.places[id(piece)] = len(self.built)
        self.built.append(node)
        self._apply_fact(node, piece)

    def _shown(self, operands: list[Expression], kinds: Kinds) -> Shown:
        """A list display: each item's term and kind."""
        items = [(self._item_term(part), self.item_kind(part)) for part in operands]
        return Shown(Lin(len(items)), kinds.kinds, kinds.every, items=items)

    def _joined(self, operands: list[Expression], kinds: Kinds) -> Joined:
        """Two lists joined by `+`: one piece whose length adds theirs."""
        left, right = (self.piece(operand) for operand in operands)
        length, split = left.length.plus(right.length), left.of_a_split or right.of_a_split
        return Joined(length, kinds.kinds, kinds.every, of_a_split=split, parts=[left, right])

    def _split(self, node: list[Expression], kinds: Kinds) -> Counted:
        """A split's list: its count, and its pieces as `split_lists` reads them. A count is
        at least as many pieces as every string has, and c* where it meets anything else."""
        listed = self.splits.made(node, self.named(node[1]))
        self.least[listed.count] = listed.least()
        if (fact := listed.fact()) != TRUE:
            self.guards.append(fact)
        if listed.read_count is not None:
            self.origin[listed.count] = listed.read_count

        def read(position: Lin, kind: str, least: Least) -> Read:
            return self.splits.read(listed, position, kind)

        return Counted(Lin.of(listed.count), kinds.kinds, kinds.every, of_a_split=True, at=read)

    def cut(self, base: Piece, bounds: list[Expression]) -> tuple[Lin, Lin] | None:
        """Where a slice of a split's list with plain bounds starts, and its length, as the
        splits write them (``Splits.sliced``); None for any other slice."""
        if not isinstance(base, Counted):
            return None
        cut = self.splits.sliced(self.splits.lists[base.length.atoms[0][0]], bounds)
        if cut is not None and (at := self.splits.values.get(cut[1].atoms[0][0])) is not None:
            self.origin[cut[1].atoms[0][0]] = at
        return cut

    def counted_compare(self, node: list[Expression]) -> str | None:
        """A compare of a split's length with a number or another length, as the splits write
        it (``Splits.compare``); None for any other part."""
        if len(node) != 3 or not isinstance(node[0], str):
            return None
        left, right = (self._side(part) for part in node[1:])
        if left is None or right is None:
            return None
        return self.splits.compare(node[0], left, right)

    def _side(self, part: Expression) -> Lin | None:
        """A side of a compare as a sum (``list_terms.summed``)."""
        return summed(part, self.length_of)

    def counts_length(self, node: list[Expression]) -> bool:
        """Whether a part is the length of a list a split's count adds to: the compares that
        name it read the count as the pieces there, so it is not defined."""
        length = self.length_of(node) if node[0] == "len" else None
        return length is not None and self.splits.reads(length)

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
        found = self._read(piece, self.position(rest[0], piece), item)
        if found.value is None:
            raise UnencodedError(f"pyct cannot render {head}: no {kind} item is read there")
        if found.guard != TRUE:
            self.guards.append(found.guard)
        if item == "str" and not isinstance(piece, Counted):
            # a split's piece is no longer than its string, which the answer holds already
            self.strings[found.value] = None
        if isinstance(piece, Stored):
            self._present(piece.length, rest[0])
        self.reads.append((operand, rest[0]))
        return found.value

    def _read(self, piece: Piece, position: Lin, item: str) -> Read:
        """The item of that kind at ``position``. A read that runs past its steps names the list
        parts it went through by their place in the order they were built, which a writing that
        settles them knows them by."""
        context = self._context()
        try:
            return read(piece, position, item, context)
        except RenderTooLargeError as error:
            passed = {self.places[at] for at in context.visited if at in self.places}
            raise RenderTooLargeError(str(error), frozenset(passed)) from error

    def start_from(self, origin: Origin, constants: Mapping[str, str]) -> None:
        """Take the values of the input whose path this is, each int leaf by its constant, which
        list parts settle their clamps as they went there, and how long a read may run."""
        for name, constant in constants.items():
            value = origin.values.get(name)
            if type(value) is int:
                self.origin[constant] = value
        self.source = origin
        self.shared = None if origin.most is None else Shared(origin.most)
        self.splits.fixed_reads = origin.fixed_reads
        self.splits.evaluated = self.origin_of
        # the value the input holds for a part it names as it is, a split's string say
        names = {constant: name for name, constant in constants.items()}
        self.splits.given = lambda part: origin.values.get(names.get(self.constant(part) or "", ""))

    def _context(self) -> Context:
        return Context(
            self.least,
            self.memo,
            self._define_read,
            ITEM_SORTS,
            self.source.until,
            self.source.steps,
            set(),
            self.shared,
            self.splits.counts,
        )

    def _define_read(self, text: str, sort: str) -> str:
        """A read written once, as ``(define-fun l!N () Sort ...)``, and named wherever read; a
        letter a spelling names is ``r!N`` (see ``letters``)."""
        key = f"{sort} {text}"
        if key not in self.written:
            name = f"l!{len(self.definitions)}"
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
            if kinds.shape is not None:
                self.origin[length] = len(kinds.shape.kinds)
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
        """A list repeated a plain number of times: one piece.

        The list the target builds is its own, and no cap holds it. The answer's lengths are
        held instead: the list repeated is no longer than it was in the input whose path this
        is, or than a million items repeated, so no answer makes the target build a list past
        both. Where that hold is what makes a path unsat, the fork is an unknown miss.
        """
        times = max(next(part for part in operands if isinstance(part, int)), 0)
        listed = self.piece(next(part for part in operands if not isinstance(part, int)))
        if times > 1 and self.source.hold:
            longest = max(self.origin_of(listed.length) or 0, MOST_ITEMS // times)
            self.capped.append(f"(assert (<= {listed.length.text()} {longest}))")
        length, split = listed.length.times(times), listed.of_a_split
        return Repeated(length, kinds.kinds, kinds.every, of_a_split=split, base=listed)

    @property
    def narrowed(self) -> bool:
        """Whether the program holds the answer to clamps settled as the input had them."""
        return bool(self.regime)

    @property
    def held(self) -> bool:
        """Whether the program holds the length of a list the target repeats."""
        return bool(self.capped)

    def asked(self) -> list[str]:
        """What the program asks cvc5 for about the lists: each length and array it declared,
        and each position's term the answer reads (see ``list_answers``)."""
        names = list(self.declared) + (self.splits.emitted if self.declared else [])
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
        each list the target repeats no longer, each read's guard, and each str item read no
        longer than a string answer holds: the strings an answer hands out, and no others."""
        lengths = [f"(assert (<= 0 {length} {MOST_ITEMS}))" for length in self.bounded]
        held = [f"(assert (>= {length} {least}))" for length, least in self.present.items()]
        guards = [f"(assert {guard})" for guard in self.guards]
        strings = [longest_string(term) for term in self.strings]
        return lengths + self.capped + list(self.regime) + held + guards + strings
