"""A join of strings written as the concatenation it is, and each split whose whole list it
joins held to its number of pieces.

Core writes a join as ``["join", sep, what]``: ``what`` is a list display of the items it read,
or a tracked list's form, whose walk the join made first. That walk's last fork,
``[">", ["len", what], n]`` taken false, says the list holds n items on every input that follows
the path to the join, so the join is ``what[0] + sep + ... + what[n-1]``, the empty string for
none. The condition means what it meant; only the way it is written changes.

The list a split hands back is plain, and render asserts only that each piece a fork reads is
there (see `splits`). A join of the whole list reads every piece, so an answer with another
piece would join another item. A split of a string the input holds, whose every piece the
join reads among its items, as ``"-".join(s.split(","))`` and ``"".join(p.upper() for p in
s.split(","))`` do, is held to the number of pieces it had in that input, by a fork the path
took, ``[COUNTED, split, n]``. Any other split is left free: one the join reads part of, as
``s.split(",")[:1]``, one it reads only as the string of another split, and one of a string the
input does not hold as it is.
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
    split whose whole list a join reads to its number of pieces.

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
    counts = rewriting.counts.values()
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
    """The parts of one path as they are rewritten, and the splits its joins read whole."""

    def __init__(self, ends: dict[_Walked, int], is_leaf: IsLeaf, held: Held) -> None:
        self.ends = ends
        self.is_leaf = is_leaf
        self.held = held
        self.written: dict[int, Expression] = {}
        # each split a join reads whole, by its identity as rewritten, and its number of pieces
        self.counts: dict[int, tuple[Node, int]] = {}

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
            self._hold_whole(items)
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

    def _hold_whole(self, items: list[Expression]) -> None:
        """Note each split every piece of which the items read, with its number of pieces."""
        read: dict[int, tuple[Node, set[int]]] = {}
        for split, at in _pieces_in(items, self.is_leaf):
            read.setdefault(id(split), (split, set()))[1].add(at)
        for key, (split, positions) in read.items():
            count = _pieces_held(split, self.held)
            if count is not None and positions >= set(range(count)):
                self.counts[key] = (split, count)


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
            case [str() as head, *_] if head in SPLITS:
                pass
            case _:
                stack.extend(part[1:])
    return found


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
