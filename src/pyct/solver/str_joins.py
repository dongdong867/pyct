"""A join of strings written as the concatenation it is, and each split whose list's end it
reads held to its number of pieces.

Core writes a join as ``["join", sep, what]``: ``what`` is a list display of the items it read,
or a tracked list's form, whose walk the join made first. That walk's last fork,
``[">", ["len", what], n]`` taken false, says the list holds n items on every input that follows
the path to the join, so the join is ``what[0] + sep + ... + what[n-1]``, the empty string for
none. The condition means what it meant; only the way it is written changes.

The list a split hands back is plain, and render asserts only that each piece a fork reads is
there (see `splits`). A join that reads a split's last piece, as ``"-".join(s.split(","))``,
``s.split(",")[1:]`` and ``reversed(s.split(","))`` do, reads to the list's end, so an answer
with another piece would join another item: such a split is held by a fork the path took,
``[COUNTED, split, n]``. For a split of a string the input holds as it is, n is the number of
pieces Python made of it there. For a split of any other string, whose pieces the solver cannot
count, n is one past the last piece the path reads, which an answer may need more of: a miss,
never an answer off the plan. A split whose last piece the join does not read, as
``s.split(",")[:1]`` from ``"q,r"``, and one the join reads only as the string of another split,
stay free: each piece is counted from the start and asserted there, so another piece past them
changes nothing the join reads.
"""

from collections.abc import Callable
from dataclasses import replace

from pyct.core.branch import Branch, Expression, IsLeaf
from pyct.solver.dag import Node, distinct
from pyct.solver.literals import plain_operand
from pyct.solver.splits import COUNTED, SPLITS

# a list a walk measured: its name, or its form's identity
type _Walked = str | int

# the value the input holds for a part it names as it is, a parameter or a value inside one;
# None for any other part
type Held = Callable[[Expression], object]


def expanded(prefix: tuple[Branch, ...], is_leaf: IsLeaf, held: Held) -> tuple[Branch, ...]:
    """The path with every join written as the concatenation it is, and a fork that holds each
    split whose list's end a join reads to its number of pieces.

    Each distinct part is rewritten once, so a part held in many places is
    still one part, and a path with no join is handed back as it is.
    """
    order, _ = distinct(prefix, is_leaf)
    if not any(node[0] == "join" for node in order):
        return prefix
    rewriting = _Rewriting(_walk_ends(prefix), is_leaf, held)
    for node in order:
        rewriting.rewrite(node)
    written = tuple(
        replace(fork, expression=rewriting.written.get(id(fork.expression), fork.expression))
        if isinstance(fork.expression, list)
        else fork
        for fork in prefix
    )
    site = prefix[-1].site
    counts = _counts(written, rewriting.reads, is_leaf, held)
    return written + tuple(Branch([COUNTED, *count], taken=True, site=site) for count in counts)


def _walk_ends(prefix: tuple[Branch, ...]) -> dict[_Walked, int]:
    """How many items each list a walk ended on holds: the n of its last fork, taken false."""
    ends: dict[_Walked, int] = {}
    for fork in prefix:
        match fork.expression:
            case [">", ["len", measured], int() as count] if not fork.taken:
                key = measured if isinstance(measured, str) else id(measured)
                ends[key] = min(ends.get(key, count), count)
    return ends


class _Rewriting:
    """The parts of one path as they are rewritten, and the pieces of splits its joins read."""

    def __init__(self, ends: dict[_Walked, int], is_leaf: IsLeaf, held: Held) -> None:
        self.ends = ends
        self.is_leaf = is_leaf
        self.held = held
        self.written: dict[int, Expression] = {}
        # each split a join reads a piece of, by its identity as rewritten, and the positions
        self.reads: dict[int, tuple[Node, set[int]]] = {}

    def rewrite(self, node: Node) -> None:
        """A part with its operands rewritten, and a join as its concatenation."""
        head, *operands = node
        parts = [self._now(part) for part in operands]
        if head == "join":
            self.written[id(node)] = self._concatenated(node, parts)
        elif any(part is not operand for part, operand in zip(parts, operands, strict=True)):
            self.written[id(node)] = [head, *parts]

    def _now(self, part: Expression) -> Expression:
        return self.written.get(id(part), part) if isinstance(part, list) else part

    def _concatenated(self, node: Node, parts: list[Expression]) -> Expression:
        """``sep.join(what)`` as its items with the separator between them."""
        separator, what = parts
        written = node[2]
        if isinstance(written, list) and written[0] == "[,]":
            items = [self._now(item) for item in written[1:]]
            for split, at in _pieces_in(items, self.is_leaf):
                self.reads.setdefault(id(split), (split, set()))[1].add(at)
        else:
            items = [["[]", what, at] for at in range(self._count(written))]
        if not items:
            return "''"
        between: list[Expression] = [items[0]]
        for item in items[1:]:
            between += [separator, item]
        return between[0] if len(between) == 1 else ["+", *between]

    def _count(self, listed: Expression) -> int:
        key = listed if isinstance(listed, str) else id(listed)
        if key not in self.ends:
            raise ValueError(f"pyct cannot render a join of {listed}: no walk ends on it")
        return self.ends[key]


def _pieces_in(items: list[Expression], is_leaf: IsLeaf) -> list[tuple[Node, int]]:
    """Each piece of a split the items read, at any depth, as its split and its position; a
    split's own string is not searched, so a piece of it is another split's material."""
    found: list[tuple[Node, int]] = []
    seen: set[int] = set()
    stack = list(items)
    while stack:
        part = stack.pop()
        if not isinstance(part, list) or is_leaf(part) or id(part) in seen:
            continue
        seen.add(id(part))
        match part:
            case ["[]", [str() as head, *_] as split, int() as at] if head in SPLITS:
                found.append((split, at))
            case _:
                stack.extend(part[1:])
    return found


def _counts(
    prefix: tuple[Branch, ...],
    reads: dict[int, tuple[Node, set[int]]],
    is_leaf: IsLeaf,
    held: Held,
) -> list[tuple[Node, int]]:
    """Each split a join reads to its list's end, with the number of pieces it is held to: the
    input's, or one past the last piece the path reads where the solver cannot count them."""
    counts: list[tuple[Node, int]] = []
    last: dict[int, int] | None = None
    for split, positions in reads.values():
        count = _pieces_held(split, held)
        if count is None:
            last = _last_pieces(prefix, is_leaf) if last is None else last
            counts.append((split, last[id(split)] + 1))
        elif max(positions) >= count - 1:
            counts.append((split, count))
    return counts


def _last_pieces(prefix: tuple[Branch, ...], is_leaf: IsLeaf) -> dict[int, int]:
    """The last piece of each split the path reads, by the split's identity."""
    last: dict[int, int] = {}
    for node in distinct(prefix, is_leaf)[0]:
        match node:
            case ["[]", [str() as head, *_] as split, int() as at] if head in SPLITS:
                last[id(split)] = max(last.get(id(split), at), at)
    return last


def _pieces_held(split: Node, held: Held) -> int | None:
    """How many pieces a split of a string the input holds made in that input, or None for a
    split of any other string."""
    text = held(split[1])
    if not isinstance(text, str):
        return None
    operands = [plain_operand(part) for part in split[2:]]
    return len(getattr(str, str(split[0]))(text, *operands))


def counted(split: Expression, term: str, count: Expression) -> str:
    """That a split, its string's term ``term``, has no piece past ``count`` pieces: piece
    ``count`` is not there.

    A partition always has three pieces, and a split or an rsplit whose
    limit allows no more than ``count`` has none past them, so either holds.
    """
    if not isinstance(split, list) or type(count) is not int:
        raise ValueError(f"pyct cannot render a count of {split}: the solver writes a split")
    head, operands = str(split[0]), tuple(plain_operand(part) for part in split[2:])
    limit = operands[1] if head in ("split", "rsplit") and len(operands) > 1 else -1
    if head == "partition" or (isinstance(limit, int) and 0 <= limit < count):
        return "true"
    _, there = SPLITS[head](term, operands, count)
    return f"(not {there})"
