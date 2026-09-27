"""A join of strings written as the concatenation it is, and each split it reads held to its
number of pieces.

Core writes a join as ``["join", sep, what]``: ``what`` is a list display of the items it read,
or a tracked list's form, whose walk the join made first. That walk's last fork,
``[">", ["len", what], n]`` taken false, says the list holds n items on every input that follows
the path to the join, so the join is ``what[0] + sep + ... + what[n-1]``, the empty string for
none. The condition means what it meant; only the way it is written changes.

The list a split hands back is plain, and render asserts only that each piece a fork reads is
there (see `splits`). A join reads the pieces it joins and no more, so an answer with another
piece would join another item. Each split a join reads, anywhere in an item, is held to one
more piece than the last of it the path reads, by a fork the path took,
``[COUNTED, split, n]``. A join that reads the whole list, as ``"-".join(s.split(","))`` does,
reads every piece, so n is the split's own number of pieces.
"""

from dataclasses import replace

from pyct.core.branch import Branch, Expression, IsLeaf
from pyct.solver.dag import Node, distinct
from pyct.solver.literals import plain_operand
from pyct.solver.splits import COUNTED, SPLITS

# a list a walk measured: its name, or its form's identity
type _Walked = str | int


def expanded(prefix: tuple[Branch, ...], is_leaf: IsLeaf) -> tuple[Branch, ...]:
    """The path with every join written as the concatenation it is, and a fork that holds each
    split a join reads to its number of pieces.

    Each distinct part is rewritten once, so a part held in many places is
    still one part, and a path with no join is handed back as it is.
    """
    order, _ = distinct(prefix, is_leaf)
    if not any(node[0] == "join" for node in order):
        return prefix
    rewriting = _Rewriting(_walk_ends(prefix), is_leaf)
    for node in order:
        rewriting.rewrite(node)
    written = tuple(
        replace(fork, expression=rewriting.written.get(id(fork.expression), fork.expression))
        if isinstance(fork.expression, list)
        else fork
        for fork in prefix
    )
    return written + _counts(written, rewriting.splits, is_leaf)


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
    """The parts of one path as they are rewritten, and the splits its joins read."""

    def __init__(self, ends: dict[_Walked, int], is_leaf: IsLeaf) -> None:
        self.ends = ends
        self.is_leaf = is_leaf
        self.written: dict[int, Expression] = {}
        # each split a join reads, by its identity as rewritten, and each part searched for one
        self.splits: dict[int, Node] = {}
        self.searched: set[int] = set()

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
        else:
            items = [["[]", what, at] for at in range(self._count(written))]
        for item in items:
            self._search(item)
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

    def _search(self, item: Expression) -> None:
        """Note each split whose piece an item reads, at any depth."""
        stack = [item]
        while stack:
            part = stack.pop()
            if not isinstance(part, list) or self.is_leaf(part) or id(part) in self.searched:
                continue
            self.searched.add(id(part))
            if (piece := _piece_of(part)) is not None:
                self.splits[id(piece[0])] = piece[0]
            stack.extend(part[1:])


def _piece_of(part: Node) -> tuple[Node, int] | None:
    """The split and the position of a split's piece, ``["[]", [split, ...], k]``; None for any
    other part."""
    match part:
        case ["[]", [str() as head, *_] as split, int() as at] if head in SPLITS:
            return split, at
    return None


def _counts(
    prefix: tuple[Branch, ...], splits: dict[int, Node], is_leaf: IsLeaf
) -> tuple[Branch, ...]:
    """A fork for each split a join reads: it has one more piece than the last the path reads."""
    if not splits:
        return ()
    last: dict[int, int] = {}
    for node in distinct(prefix, is_leaf)[0]:
        piece = _piece_of(node)
        if piece is not None and id(piece[0]) in splits:
            key, at = id(piece[0]), piece[1]
            last[key] = max(last.get(key, at), at)
    site = prefix[-1].site
    return tuple(
        Branch(expression=[COUNTED, split, last[key] + 1], taken=True, site=site)
        for key, split in splits.items()
    )


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
