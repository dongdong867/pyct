"""A join of strings written as the concatenation it is.

Core writes a join as ``["join", sep, what]``: ``what`` is a list display of the items it read,
or a tracked list's form, whose walk the join made first. That walk's last fork,
``[">", ["len", what], n]`` taken false, says the list holds n items on every input that follows
the path to the join, so the join is ``what[0] + sep + ... + what[n-1]``, the empty string for
none. The condition means what it meant; only the way it is written changes. A split's list is
a tracked list, so its walk fixes how many pieces the join holds, as any list's does
(follow-the-length-of-a-split).
"""

from dataclasses import replace

from pyct.core.branch import Branch, Expression, IsLeaf
from pyct.solver.dag import Node, distinct

# a list a walk measured: its name, or its form's identity
type _Walked = str | int


def expanded(prefix: tuple[Branch, ...], is_leaf: IsLeaf) -> tuple[Branch, ...]:
    """The path with every join written as the concatenation it is.

    Each distinct part is rewritten once, so a part held in many places is
    still one part, and a path with no join is handed back as it is.
    """
    order, _ = distinct(prefix, is_leaf)
    if not any(node[0] == "join" for node in order):
        return prefix
    rewriting = _Rewriting(_walk_ends(prefix))
    for node in order:
        rewriting.rewrite(node)
    return tuple(
        replace(fork, expression=rewriting.written.get(id(fork.expression), fork.expression))
        if isinstance(fork.expression, list)
        else fork
        for fork in prefix
    )


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
    """The parts of one path as they are rewritten."""

    def __init__(self, ends: dict[_Walked, int]) -> None:
        self.ends = ends
        self.written: dict[int, Expression] = {}

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
