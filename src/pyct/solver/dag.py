"""A path's conditions as Python holds them: lists that share their parts.

A tracked value's expression holds the expressions it was built from as
they are, so a string rebuilt from two pieces of itself holds the old
expression twice, as one list. Walked as a tree, such a condition doubles
with every pass of the loop that built it; walked by identity, each list is
met once.
"""

from pyct.core.branch import Branch, Expression

# a list of the path, as the walk meets it
type Node = list[Expression]


def distinct(prefix: tuple[Branch, ...]) -> tuple[list[Node], dict[int, int]]:
    """Every distinct list in the path's conditions, each before any list that holds it.

    Also how many places hold each list, keyed by its identity: a fork's
    condition is held once by the fork, and an operand once for each place
    a list holds it. Each list is walked once, without recursion.
    """
    order: list[Node] = []
    holders: dict[int, int] = {}
    stack: list[tuple[Node, bool]] = []
    for fork in reversed(prefix):
        if isinstance(fork.expression, list):
            holders[id(fork.expression)] = holders.get(id(fork.expression), 0) + 1
            stack.append((fork.expression, False))
    seen: set[int] = set()
    while stack:
        node, finished = stack.pop()
        if finished:
            order.append(node)
        elif id(node) not in seen:
            seen.add(id(node))
            stack.append((node, True))
            # the leftmost operand on top, so the walk meets the operands in written order
            stack.extend((part, False) for part in reversed(_held(node, holders)))
    return order, holders


def _held(node: Node, holders: dict[int, int]) -> list[Node]:
    """The lists a list holds as operands, each counted as held once more."""
    parts = [part for part in node[1:] if isinstance(part, list)]
    for part in parts:
        holders[id(part)] = holders.get(id(part), 0) + 1
    return parts
