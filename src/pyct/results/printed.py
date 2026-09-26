"""The cap on what a line prints of a fork's expression.

A printed expression holds at most `LIMIT` nodes: every list is one node,
and so is every leaf. Past the limit, the top of the expression is kept and
each part cut from it is written ``["...", N]``, N being how many nodes that
part stands for. Only the printing is cut: the solver gets the whole
condition. The stdout line and the stderr fork line both print what
`printed` hands them (``README.md › Rules › the stdout line``).
"""

from collections import deque

from pyct.core.branch import Expression

# the most nodes a printed expression holds
LIMIT = 1000

# the head of a cut part, `["...", N]`
CUT = "..."

# what a cut part costs on the line: its list and the count it carries
_CUT_NODES = 2

# a part still to open: the list the line holds for it, and the part itself
type _Pending = tuple[list[Expression], list[Expression]]


def printed(expression: Expression) -> Expression:
    """The expression as a line prints it: whole within `LIMIT` nodes, else cut down to it.

    Nodes are counted over the expression as it sits in memory, where a part
    Python used twice is one shared list. A loop that rebuilds a string from
    two pieces of itself doubles the expression written out on every pass,
    and it is counted without being written out.
    """
    sizes = _sizes(expression)
    if not isinstance(expression, list) or sizes[id(expression)] <= LIMIT:
        return expression
    return _cut(expression, sizes)


def _cut(expression: list[Expression], sizes: dict[int, int]) -> Expression:
    """The top of the expression, opened breadth first while the line has room.

    Every part starts cut. Shallowest first, and under one operator its
    smaller operands before its larger ones, a cut part is written whole if
    it fits, else opened to its operator if that fits, else left cut. The
    order is fixed, so an expression is cut the same way every time.
    """
    root: list[Expression] = [CUT, sizes[id(expression)]]
    spent = _CUT_NODES
    queue: deque[_Pending] = deque([(root, expression)])
    while queue:
        slot, part = queue.popleft()
        whole = sizes[id(part)]
        if spent - _CUT_NODES + whole <= LIMIT:
            slot[:] = part
            spent += whole - _CUT_NODES
            continue
        opened, cost, pending = _opened(part, sizes)
        if spent - _CUT_NODES + cost <= LIMIT:
            slot[:] = opened
            spent += cost - _CUT_NODES
            queue.extend(pending)
    return root


def _opened(
    part: list[Expression], sizes: dict[int, int]
) -> tuple[list[Expression], int, list[_Pending]]:
    """A part opened to its operator: what the line holds, what it costs, and what stays cut.

    An operand no larger than a cut part is written whole; each larger one
    is cut, and waits to be opened in turn, smallest first.
    """
    head, *operands = part
    opened: list[Expression] = [head]
    pending: list[_Pending] = []
    for operand in operands:
        if isinstance(operand, list) and sizes[id(operand)] > _CUT_NODES:
            stand_in: list[Expression] = [CUT, sizes[id(operand)]]
            opened.append(stand_in)
            pending.append((stand_in, operand))
        else:
            opened.append(operand)
    cost = 1 + sum(min(_size(operand, sizes), _CUT_NODES) for operand in operands)
    return opened, cost, sorted(pending, key=lambda waiting: sizes[id(waiting[1])])


def _size(expression: Expression, sizes: dict[int, int]) -> int:
    """How many nodes an expression holds written out: a leaf is one."""
    return sizes[id(expression)] if isinstance(expression, list) else 1


def _sizes(expression: Expression) -> dict[int, int]:
    """How many nodes each list in the expression holds written out, keyed by its identity.

    Each list is counted once however many parts share it, and without
    recursion, so neither a deep expression nor a shared one costs more
    than one step per list.
    """
    sizes: dict[int, int] = {}
    stack: list[tuple[list[Expression], bool]] = (
        [(expression, False)] if isinstance(expression, list) else []
    )
    while stack:
        part, counted = stack.pop()
        if counted:
            sizes[id(part)] = 1 + sum(_size(operand, sizes) for operand in part[1:])
        elif id(part) not in sizes:
            stack.append((part, True))
            stack.extend((operand, False) for operand in part[1:] if isinstance(operand, list))
    return sizes
