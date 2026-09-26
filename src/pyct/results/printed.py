"""The cap on what a line prints of a fork's expression.

A printed expression holds at most `LIMIT` nodes, counted as the line
writes them: every list is one node, and so is every leaf, and a part
Python shares is written, and counted, at each place that holds it. Past
the limit, the top of the expression is kept and each part cut from it is
written ``["...", N]``, N being how many distinct nodes that part holds: a
list the part reaches more than once counts once, with its leaves. So N
stays near the number of operations that built the part, however often the
part repeats written out. Only the printing is cut: the solver gets the
whole condition. The stdout line and the stderr fork line both print what
`printed_forks` hands them, cut once for the two (``README.md › Rules ›
the stdout line``).
"""

from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass

from pyct.core.branch import Branch, Expression

# the most nodes a printed expression holds, as the line writes them
LIMIT = 1000

# the head of a cut part, `["...", N]`
CUT = "..."

# what a cut part costs on the line: its list and the count it carries
_CUT_NODES = 2

# a part still to open: the list the line holds for it, and the part itself
type _Pending = tuple[list[Expression], list[Expression]]

# a list of an expression, as the walk meets it
type _Node = list[Expression]

# the nodes a list reaches, by their numbers in the walk: the lowest number, and bits from it,
# bit k set for number lowest + k. Kept from the lowest number up, a reach is as wide as the
# numbers it spans, not as the walk so far
type _Reach = tuple[int, int]


@dataclass(frozen=True)
class _Counts:
    """Two counts of every list the expressions hold, keyed by its identity.

    ``written`` is how many nodes a list holds written out, as the line would
    write it whole, so it decides what fits. ``distinct`` is how many distinct
    nodes it reaches, each counted once, so it is what a cut part says.
    """

    written: dict[int, int]
    distinct: dict[int, int]


def printed(expression: Expression) -> Expression:
    """The expression as a line prints it: whole within `LIMIT` nodes, else cut down to it.

    Nodes are counted over the expression as it sits in memory, where a part
    Python used twice is one shared list. A loop that rebuilds a string from
    two pieces of itself doubles the expression written out on every pass,
    and it is counted without being written out.
    """
    return _printed_all((expression,))[0]


def printed_forks(forks: Sequence[Branch]) -> tuple[Expression, ...]:
    """Each fork's expression as `printed` prints it, every list counted once for all the forks.

    A loop's forks each hold its string as that pass left it, so each holds
    the string of every fork before it. Counted fork by fork, a path would
    cost its length times its size; counted once, it costs its size. The
    forks keep their expressions, so each list keeps its identity while the
    count is read.
    """
    return _printed_all(tuple(fork.expression for fork in forks))


def _printed_all(expressions: tuple[Expression, ...]) -> tuple[Expression, ...]:
    """Each expression whole within `LIMIT` nodes, else cut down to it, all counted together."""
    counts = _counted(*_walked(expressions))
    return tuple(
        _cut(expression, counts)
        if isinstance(expression, list) and counts.written[id(expression)] > LIMIT
        else expression
        for expression in expressions
    )


def _cut(expression: list[Expression], counts: _Counts) -> Expression:
    """The top of the expression, opened breadth first while the line has room.

    Every part starts cut. Shallowest first, and under one operator its
    smaller operands before its larger ones, a cut part is written whole if
    it fits, else opened to its operator if that fits, else left cut. The
    order is fixed, so an expression is cut the same way every time.
    """
    root: list[Expression] = [CUT, counts.distinct[id(expression)]]
    spent = _CUT_NODES
    queue: deque[_Pending] = deque([(root, expression)])
    while queue:
        slot, part = queue.popleft()
        whole = counts.written[id(part)]
        if spent - _CUT_NODES + whole <= LIMIT:
            slot[:] = part
            spent += whole - _CUT_NODES
            continue
        opened, cost, pending = _opened(part, counts)
        if spent - _CUT_NODES + cost <= LIMIT:
            slot[:] = opened
            spent += cost - _CUT_NODES
            queue.extend(pending)
    return root


def _opened(
    part: list[Expression], counts: _Counts
) -> tuple[list[Expression], int, list[_Pending]]:
    """A part opened to its operator: what the line holds, what it costs, and what stays cut.

    An operand no larger written out than a cut part is written whole; each
    larger one is cut, and waits to be opened in turn, smallest first.
    """
    head, *operands = part
    written = [
        counts.written[id(operand)] if isinstance(operand, list) else 1 for operand in operands
    ]
    opened: list[Expression] = [head]
    pending: list[_Pending] = []
    for operand, size in zip(operands, written, strict=True):
        if isinstance(operand, list) and size > _CUT_NODES:
            stand_in: list[Expression] = [CUT, counts.distinct[id(operand)]]
            opened.append(stand_in)
            pending.append((stand_in, operand))
        else:
            opened.append(operand)
    cost = 1 + sum(min(size, _CUT_NODES) for size in written)
    return opened, cost, sorted(pending, key=lambda waiting: counts.written[id(waiting[1])])


def _walked(expressions: tuple[Expression, ...]) -> tuple[list[_Node], dict[int, int]]:
    """Every distinct list the expressions hold, each after the lists it holds.

    Also how many places in those lists hold each list, keyed by its
    identity. Each list is walked once however many parts share it, and
    without recursion, so neither a deep expression nor a shared one costs
    more than one step per list.
    """
    order: list[_Node] = []
    holders: dict[int, int] = {}
    seen: set[int] = set()
    stack = [(part, False) for part in reversed(expressions) if isinstance(part, list)]
    while stack:
        node, finished = stack.pop()
        if finished:
            order.append(node)
        elif id(node) not in seen:
            seen.add(id(node))
            stack.append((node, True))
            held = [part for part in node[1:] if isinstance(part, list)]
            for part in held:
                holders[id(part)] = holders.get(id(part), 0) + 1
            stack.extend((part, False) for part in held)
    return order, holders


def _counted(order: list[_Node], holders: dict[int, int]) -> _Counts:
    """Both counts of every list, each worked out once, after the lists it holds.

    A list's own nodes are itself and its leaves, and each list gets numbers
    of its own in one numbering. What a list reaches is its own numbers and
    those each list it holds reaches, so the distinct nodes are the numbers
    reached, a list reached twice adding the same numbers. A list's reach is
    kept only until every place that holds it has read it.
    """
    written: dict[int, int] = {}
    distinct: dict[int, int] = {}
    reached: dict[int, _Reach] = {}
    unread = dict(holders)
    first = 0
    for node in order:
        held = [part for part in node[1:] if isinstance(part, list)]
        own = len(node) - len(held)
        reach: _Reach = (first, (1 << own) - 1)
        first += own
        for part in held:
            reach = _joined(reach, reached[id(part)])
            unread[id(part)] -= 1
            if not unread[id(part)]:
                del reached[id(part)]
        written[id(node)] = own + sum(written[id(part)] for part in held)
        distinct[id(node)] = reach[1].bit_count()
        if unread.get(id(node)):
            reached[id(node)] = reach
    return _Counts(written=written, distinct=distinct)


def _joined(reach: _Reach, other: _Reach) -> _Reach:
    """Two reaches as one, numbered from the lower of their lowest numbers."""
    (low, bits), (other_low, other_bits) = reach, other
    if other_low < low:
        return other_low, (bits << (low - other_low)) | other_bits
    return low, bits | (other_bits << (other_low - low))
