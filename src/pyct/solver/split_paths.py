"""The splits' lists of one path: each split's count, how a compare reads it, the number c* it
is where it meets anything else, and whether a read held a string to c* pieces (see
``split_lists``)."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from pyct.core.branch import Branch, Expression
from pyct.core.str_splits import LISTED_SPLITS
from pyct.solver.list_terms import FALSE, TRUE, Lin, Read, both, compare, negated
from pyct.solver.literals import plain_operand
from pyct.solver.split_lists import SplitList, SplitRead

# how each order on two ints reads as a compare of the lower with the higher: whether the
# operands swap, and whether they may be equal
_ORDERS: Mapping[str, tuple[bool, bool]] = {
    "<": (False, False),
    "<=": (False, True),
    ">": (True, False),
    ">=": (True, True),
}

# each compare on two ints, as Python takes it
_COMPARES: Mapping[str, Callable[[int, int], bool]] = {
    "<": lambda left, right: left < right,
    "<=": lambda left, right: left <= right,
    ">": lambda left, right: left > right,
    ">=": lambda left, right: left >= right,
    "==": lambda left, right: left == right,
    "!=": lambda left, right: left != right,
}

# plain arithmetic on a count with a plain int, as Python takes it
_ARITHMETIC: Mapping[str, Callable[[int, int], int]] = {
    "+": lambda left, right: left + right,
    "-": lambda left, right: left - right,
    "*": lambda left, right: left * right,
}

# how far from the input's own count c* is looked for: past it, the path's compares with plain
# ints rule out every count near the input's, and c* stays the input's own
_FARTHEST = 10_000

# how deep a compare's side may nest arithmetic and still be read as a split's count: a loop
# that adds on every pass nests thousands deep, which no compare of a count does
_SUM_DEPTH = 8

# what a side of a compare is: the split whose count it reads, and its value at each count
type Counting = tuple[list[Expression], Callable[[int], int]]


class Splits:
    """The splits' lists of one path: each by its count's name and by its part, how a compare
    reads each count and each slice's length of one, and the number each is where a term of
    the program reads it."""

    def __init__(self) -> None:
        self.lists: dict[str, SplitList] = {}
        self.parts: dict[int, str] = {}
        self.counts: dict[str, Callable[[int], str]] = {}
        # each count's c*, and each slice's length at it, by name; None where not known
        self.values: dict[str, int | None] = {}
        self.emitted: list[str] = []
        # the value the input holds for a part it names as it is, a split's string say, and a
        # position's value in that input
        self.given: Callable[[Expression], object] = lambda part: None
        self.evaluated: Callable[[Lin], int | None] = lambda position: None
        # whether a piece read from the end, where no walk of the reversed string reads it,
        # holds its string to c* pieces, and whether a read did
        self.fixed_reads = True
        self.fixed = False
        # what each fork on a split's own count, through plain arithmetic with plain ints,
        # says the count is, by the split's part
        self.conditions: dict[int, list[Callable[[int], bool]]] = {}
        # each slice's length that is its split's count less a plain start, wherever the slice
        # holds an item, by name: the split's count and the start
        self.tails: dict[str, tuple[str, int]] = {}
        # each slice's start that is where c* puts it, by name: the split and the slice
        self.starts: dict[str, tuple[SplitList, slice]] = {}

    def learn(self, prefix: tuple[Branch, ...]) -> None:
        """What each fork that compares a split's count, through plain arithmetic, with a plain
        int says of the count, the side it took included."""
        for fork in prefix:
            found = _condition(fork)
            if found is not None:
                split, holds = found
                self.conditions.setdefault(id(split), []).append(holds)

    def made(self, node: list[Expression], term: str) -> SplitList:
        """A split's list, its string's term ``term``, with how many pieces Python makes of the
        string in the input whose path this is, where its value is known, and c*."""
        head, string, *operands = node
        plain = tuple(plain_operand(part) for part in operands)
        text = _text(string, self.given)
        held = len(getattr(str, str(head))(text, *plain)) if isinstance(text, str) else None
        listed = SplitList(
            term=term,
            head=str(head),
            operands=plain,
            count=f"count!{len(self.lists)}!",
            input_count=held,
            read_count=self._read_count(node, held),
            fixed=self.fixed_reads,
        )
        self.lists[listed.count] = listed
        self.parts[id(node)] = listed.count
        self.counts[listed.count] = listed.past
        self.values[listed.count] = listed.read_count
        return listed

    def _read_count(self, node: list[Expression], held: int | None) -> int | None:
        """c*: the input's own count, or the count nearest it that every fork on the split's
        count through plain arithmetic with a plain int allows."""
        if held is None:
            return None
        conditions = self.conditions.get(id(node), [])
        for away in range(_FARTHEST):
            for near in (held + away, held - away):
                if near >= 0 and all(holds(near) for holds in conditions):
                    return near
        return held

    def sliced(self, listed: SplitList, bounds: list[Expression]) -> tuple[Lin, Lin] | None:
        """Where a slice of a split's list with plain bounds and a step of 1 or -1 starts, and
        its length: a start from the start, or the last piece for a slice that steps back from
        the end, is exact on every string, and any other is a name of its own, which a read
        takes where c* puts it, the string held to c* pieces (see ``read``); the length is
        ``cut``'s. None for any other slice."""
        plain = [bound for bound in bounds if bound is None or type(bound) is int]
        start, stop, step = (*plain, None, None, None)[:3]
        if len(plain) != len(bounds) or len(bounds) > 3 or step not in (None, 1, -1):
            return None
        assert start is None or isinstance(start, int)
        assert stop is None or isinstance(stop, int)
        length = self.cut(listed, (start, stop, step))
        if stop is None and step != -1 and (start is None or start >= 0):
            # a slice that holds an item is that many pieces short of the split
            self.tails[length.atoms[0][0]] = (listed.count, start or 0)
        if step == -1 and start is None:
            return Lin.of(listed.count).minus(Lin(1)), length
        if step != -1 and (start is None or start >= 0):
            return Lin(start or 0), length
        if listed.read_count is None:
            return None
        window = slice(start, stop, step)
        name = f"start!{len(self.values)}!"
        self.starts[name] = (listed, window)
        self.values[name] = window.indices(listed.read_count)[0]
        return Lin.of(name), length

    def cut(self, listed: SplitList, bounds: tuple[int | None, ...]) -> Lin:
        """The length of a slice of a split's list with plain bounds, as a name of its own that
        a compare with a number reads as whether a piece is there, exact on every string."""
        name = f"cut!{len(self.values)}!"
        window = slice(*bounds)
        self.counts[name] = lambda number: _cut_past(listed.past, window, number)
        at = listed.read_count
        self.values[name] = None if at is None else len(range(*window.indices(at)))
        return Lin.of(name)

    def read(self, listed: SplitList, position: Lin, kind: str) -> Read:
        """A split's piece at ``position``, noting whether the read held the string to c*."""
        started = self._started(listed, position, kind)
        read = started or listed.read(self._counted_back(position), kind, self.evaluated(position))
        self.fixed |= read.fixes_the_count
        return read.found

    def _started(self, listed: SplitList, position: Lin, kind: str) -> SplitRead | None:
        """A piece read through a slice whose start is where c* puts it: there, the string held
        to c* pieces, or, with ``fixed_reads`` false, where the input's own count puts it with
        no count held, as origin/v2 reads it; None for any other position."""
        if len(position.atoms) != 1 or position.atoms[0][1] != 1 or kind != "str":
            return None
        start = self.starts.get(position.atoms[0][0])
        if start is None:
            return None
        window = start[1]
        if self.fixed_reads and listed.read_count is not None:
            return listed.held_at(window.indices(listed.read_count)[0] + position.const)
        own = listed.input_count
        if own is None:
            return SplitRead(Read(None, FALSE))
        return SplitRead(listed.at(window.indices(own)[0] + position.const))

    def _counted_back(self, position: Lin) -> Lin:
        """A position counted back from the end of a slice that runs to the split's end, as
        the same position counted back from the split's own end: the slice holds the item read
        there, so it is that many pieces short of the split."""
        if len(position.atoms) != 1 or position.atoms[0][1] != 1:
            return position
        tail = self.tails.get(position.atoms[0][0])
        if tail is None:
            return position
        count, start = tail
        return Lin.of(count).plus(Lin(position.const - start))

    def flags(self) -> dict[str, bool]:
        """What a program's splits say of it: whether a read held a string to c* pieces, which
        an unsat or unknown answer asks again (see `solver.cvc5`)."""
        return {"fixed": self.fixed}

    def count_of(self, node: list[Expression]) -> str:
        """The name of a split's count."""
        return self.parts[id(node)]

    def reads(self, term: Lin) -> bool:
        """Whether a term adds a split's count."""
        return any(atom in self.counts for atom, _ in term.atoms)

    def compare(self, head: str, left: Lin, right: Lin) -> str | None:
        """``left head right`` where a side adds a split's count: whether the split holds a
        piece, where the other side is a number; None for any other compare.

        The least values the path's own forks give are not read here: this compare is one of
        those forks, which the program asserts.
        """
        if head not in (*_ORDERS, "==", "!=") or not (self.reads(left) or self.reads(right)):
            return None
        if head in ("==", "!="):
            below = compare(left, right, {}, or_equal=True, counts=self.counts)
            same = both(below, compare(right, left, {}, or_equal=True, counts=self.counts))
            return same if head == "==" else negated(same)
        swap, or_equal = _ORDERS[head]
        low, high = (right, left) if swap else (left, right)
        return compare(low, high, {}, or_equal=or_equal, counts=self.counts)

    def defined(self, lines: list[str]) -> list[str]:
        """Each count, and each slice's length of one, that a line of the program reads as a
        term, as its c*: a number where the input's own count is known, or else a count no
        tie holds."""
        text = "\n".join(lines)
        written: list[str] = []
        for name, value in self.values.items():
            if name not in text or name in self.emitted:
                continue
            self.emitted.append(name)
            if value is None:
                written += [f"(declare-const {name} Int)", f"(assert (>= {name} 0))"]
            else:
                written.append(f"(define-fun {name} () Int {value})")
        return written


def _condition(fork: Branch) -> tuple[list[Expression], Callable[[int], bool]] | None:
    """The split a fork compares the count of, through plain arithmetic, with a plain int, and
    whether a count takes the fork's side; None for any other fork."""
    expression = fork.expression
    if not isinstance(expression, list) or len(expression) != 3:
        return None
    test = _COMPARES.get(str(expression[0]))
    left, right = expression[1], expression[2]
    if test is None or (type(left) is int) == (type(right) is int):
        return None
    side = _counting(left) if type(right) is int else _counting(right)
    if side is None:
        return None
    split, value = side
    number = right if type(right) is int else left
    assert isinstance(number, int)
    if type(right) is int:
        return split, lambda at: test(value(at), number) is fork.taken
    return split, lambda at: test(number, value(at)) is fork.taken


def _text(part: Expression, given: Callable[[Expression], object]) -> object:
    """A string's value in the input whose path this is: a name's, or a str method with plain
    operands called on one, `s.strip()` say; None where neither."""
    value = given(part)
    if value is not None or not isinstance(part, list) or len(part) < 2:
        return value
    head, string, *operands = part
    method = getattr(str, head, None) if isinstance(head, str) else None
    if not callable(method) or any(isinstance(operand, list) for operand in operands):
        return None
    text = _text(string, given)
    if not isinstance(text, str):
        return None
    try:
        plain = [plain_operand(operand) for operand in operands]
    except ValueError:
        return None
    try:
        value = method(text, *plain)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, str) else None


def _counting(part: Expression, depth: int = _SUM_DEPTH) -> Counting | None:
    """A side of a compare that reads a split's count, ``len(parts)``, the length of a slice of
    it with plain bounds, or either through `+`, `-` or `*` with a plain int, nested at most
    ``depth`` deep, and its value at each count; None for any other side."""
    if not isinstance(part, list) or len(part) not in (2, 3):
        return None
    if part[0] == "len" and len(part) == 2:
        return _measured(part[1])
    combine = _ARITHMETIC.get(str(part[0]))
    if combine is None or len(part) != 3 or depth == 0:
        return None
    left, right = part[1], part[2]
    if type(right) is int and (side := _counting(left, depth - 1)) is not None:
        split, value = side
        return split, lambda at: combine(value(at), right)
    if type(left) is int and (side := _counting(right, depth - 1)) is not None:
        split, value = side
        return split, lambda at: combine(left, value(at))
    return None


def _measured(form: Expression) -> Counting | None:
    """A split's list, or a slice of it with plain bounds, and its length at each count."""
    if not isinstance(form, list) or not form:
        return None
    if form[0] in LISTED_SPLITS:
        return form, lambda at: at
    inner = form[1] if len(form) > 2 else None
    bounds = form[2:]
    plain = all(bound is None or type(bound) is int for bound in bounds)
    if form[0] != "[:]" or not plain or not isinstance(inner, list) or not inner:
        return None
    if inner[0] not in LISTED_SPLITS:
        return None
    window = slice(*bounds)
    return inner, lambda at: len(range(*window.indices(at)))


def _cut_past(past: Callable[[int], str], window: slice, number: int) -> str:
    """That a slice of a split's list holds more items than ``number``: as Python slices, for
    each run of counts that make it that long, the split holding at least the first and no
    more than the last. Past ``reach`` every bound counts from where it does at any count, so
    the length grows, shrinks or stays with the count, and the last run is open there."""
    if number < 0:
        return TRUE
    reach = number + 2 + sum(abs(bound) for bound in (window.start, window.stop) if bound)
    long = [len(range(*window.indices(at))) > number for at in range(reach + 1)]
    runs: list[str] = []
    first = TRUE
    for at, inside in enumerate(long):
        if inside and (at == 0 or not long[at - 1]):
            first = past(at - 1)
        if inside and (at == reach or not long[at + 1]):
            runs.append(first if at == reach else both(first, negated(past(at))))
    if not runs:
        return FALSE
    return runs[0] if len(runs) == 1 else f"(or {' '.join(runs)})"
