"""The cap on what a line prints of a fork's expression.

A printed expression holds at most `LIMIT` nodes, counted as the line
writes them: every list is one node, and so is every leaf, and a part
Python shares is written, and counted, at each place that holds it. Past
the limit, the top of the expression is kept and each part cut from it is
written ``["...", N]``, N being how many distinct nodes that part holds: a
list the part reaches more than once counts once, with its leaves. So N
stays near the number of operations that built the part, however often the
part repeats written out. N is ``None``, ``null`` on the line, when counting
it would take more than `COUNTING_STEPS`. Only the printing is cut: the
solver gets the whole condition. The stdout line and the stderr fork line
both print what `printed_forks` hands them, cut once for the two
(``README.md › Rules › the stdout line``).
"""

import math
from collections import deque
from collections.abc import Sequence

from pyct.core.branch import Branch, Expression

# the most nodes a printed expression holds, as the line writes them
LIMIT = 1000

# the head of a cut part, `["...", N]`
CUT = "..."

# the most steps counting a line's cut parts may take (see `_Steps`). Where it was measured, a
# step took at most about 0.12 µs, and counting that spent them all took 0.25 s at most. That
# still counts every cut part of the loops the tests run: the edit loop at 2,000 passes in
# about 114,000 steps, a chain with a fork on each of 20,000 steps in about 230,000, and
# 40,000 characters gathered into one string, the most, in about 1.73 million
COUNTING_STEPS = 2**21

# what a cut part costs on the line: its list and the count it carries
_CUT_NODES = 2

# a list of an expression, as the walk meets it
type _Node = list[Expression]

# a part still to open: the list the line holds for it, and the part itself. A part left cut
# keeps the same pair, so its count can be written into the list once it is known
type _Pending = tuple[list[Expression], _Node]

# a stretch of the numbers a list reaches: the lowest number, and bits from it, bit k set for
# number lowest + k
type _Run = tuple[int, int]

# the nodes a list reaches, by their numbers in the walk: runs in order, apart by more than
# `_GAP`. A reach is as wide as the numbers it holds, not as the walk so far, where a list
# that reaches one shared early part would span everything numbered since
type _Reach = tuple[_Run, ...]

# how many numbers two runs may leave between them and still be kept as one: a word of zero
# bits costs less than a run of its own
_GAP = 64

# the bits of a run one step merges: 128 machine words, which C merges in about the time Python
# takes to handle one run
_BITS_PER_STEP = 8192


class _StepsSpentError(Exception):
    """Counting reached its limit of steps. The count it was working on stays unknown."""


class _Steps:
    """What counting a line may still spend, in steps.

    A step is one list, one operand of a list or one run handled in Python,
    or `_BITS_PER_STEP` bits of a run merged or counted in C: each costs a
    small, fixed time, so a limit on steps is a limit on time.
    """

    def __init__(self, allowed: float) -> None:
        self.left = allowed

    def spend(self, steps: int) -> None:
        """Take the steps, or raise `_StepsSpentError`, taking none, when fewer are left."""
        if steps > self.left:
            raise _StepsSpentError
        self.left -= steps


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
    """Each expression whole within `LIMIT` nodes, else cut down to it, all counted together.

    The cost, for L distinct lists holding E operands between them, F forks
    and C = `COUNTING_STEPS`: the walk and the written sizes take O(L + E)
    steps, cutting takes O(`LIMIT`) steps a fork, and counting what the cut
    parts hold takes at most C steps, whatever the sharing, sorting a list's
    runs adding at most a log factor. Counting what each part reaches is as
    hard as finding two orthogonal vectors, so no count that is always exact
    runs in less than about quadratic time; the limit on C is what bounds it.
    So a line costs O(L + E + F * `LIMIT` + C log C).
    """
    written = _written(_walked(expressions, _Steps(math.inf))[0])
    cuts: list[_Pending] = []
    shown = tuple(
        _cut(expression, written, cuts)
        if isinstance(expression, list) and written[id(expression)] > LIMIT
        else expression
        for expression in expressions
    )
    parts = tuple({id(part): part for _, part in cuts}.values())
    distinct = _counted(*_walked(parts, steps := _Steps(COUNTING_STEPS)), steps)
    for stand_in, part in cuts:
        stand_in[1] = distinct.get(id(part))
    return shown


def _cut(expression: _Node, written: dict[int, int], cuts: list[_Pending]) -> Expression:
    """The top of the expression, opened breadth first while the line has room.

    Every part starts cut. Shallowest first, and under one operator its
    smaller operands before its larger ones, a cut part is written whole if
    it fits, else opened to its operator if that fits, else left cut, and
    added to ``cuts``. The order is fixed, so an expression is cut the same
    way every time.
    """
    root: list[Expression] = [CUT, None]
    spent = _CUT_NODES
    queue: deque[_Pending] = deque([(root, expression)])
    while queue:
        slot, part = queue.popleft()
        whole = written[id(part)]
        if spent - _CUT_NODES + whole <= LIMIT:
            slot[:] = part
            spent += whole - _CUT_NODES
            continue
        opened, cost, pending = _opened(part, written)
        if spent - _CUT_NODES + cost <= LIMIT:
            slot[:] = opened
            spent += cost - _CUT_NODES
            queue.extend(pending)
        else:
            cuts.append((slot, part))
    return root


def _opened(part: _Node, written: dict[int, int]) -> tuple[_Node, int, list[_Pending]]:
    """A part opened to its operator: what the line holds, what it costs, and what stays cut.

    An operand no larger written out than a cut part is written whole; each
    larger one is cut, and waits to be opened in turn, smallest first.
    """
    head, *operands = part
    sizes = [written[id(operand)] if isinstance(operand, list) else 1 for operand in operands]
    opened: list[Expression] = [head]
    pending: list[_Pending] = []
    for operand, size in zip(operands, sizes, strict=True):
        if isinstance(operand, list) and size > _CUT_NODES:
            stand_in: list[Expression] = [CUT, None]
            opened.append(stand_in)
            pending.append((stand_in, operand))
        else:
            opened.append(operand)
    cost = 1 + sum(min(size, _CUT_NODES) for size in sizes)
    return opened, cost, sorted(pending, key=lambda waiting: written[id(waiting[1])])


def _walked(
    expressions: tuple[Expression, ...], steps: _Steps
) -> tuple[list[_Node], dict[int, int]]:
    """Every distinct list the expressions hold, each after the lists it holds.

    Also how many places in those lists hold each list, keyed by its
    identity. Each list is walked once however many parts share it, and
    without recursion. The walk spends a step on each list and each operand;
    when the steps run out it stops, and the lists it finished are the ones
    it hands back.
    """
    order: list[_Node] = []
    holders: dict[int, int] = {}
    seen: set[int] = set()
    stack = [(part, False) for part in reversed(expressions) if isinstance(part, list)]
    try:
        while stack:
            node, finished = stack.pop()
            if finished:
                order.append(node)
            elif id(node) not in seen:
                steps.spend(len(node))
                seen.add(id(node))
                stack.append((node, True))
                held = [part for part in node[1:] if isinstance(part, list)]
                for part in held:
                    holders[id(part)] = holders.get(id(part), 0) + 1
                stack.extend((part, False) for part in held)
    except _StepsSpentError:
        pass
    return order, holders


def _written(order: list[_Node]) -> dict[int, int]:
    """How many nodes each list holds written out, keyed by its identity: what the line would
    hold for it whole."""
    written: dict[int, int] = {}
    for node in order:
        written[id(node)] = 1 + sum(
            written[id(part)] if isinstance(part, list) else 1 for part in node[1:]
        )
    return written


def _counted(order: list[_Node], holders: dict[int, int], steps: _Steps) -> dict[int, int]:
    """How many distinct nodes each list reaches, keyed by its identity, after the lists it holds.

    A list's own nodes are itself and its leaves, and each list gets numbers
    of its own in one numbering. What a list reaches is its own numbers and
    those each list it holds reaches, so the distinct nodes are the numbers
    reached, a list reached twice adding the same numbers. A list's reach is
    kept only until every place that holds it has read it. When the steps run
    out, the lists counted so far keep their counts and the rest have none.
    """
    distinct: dict[int, int] = {}
    reached: dict[int, _Reach] = {}
    unread = dict(holders)
    first = 0
    try:
        for node in order:
            reach, first = _reach(node, first, reached, unread, steps)
            distinct[id(node)] = sum(bits.bit_count() for _, bits in reach)
            if unread.get(id(node)):
                reached[id(node)] = reach
    except _StepsSpentError:
        pass
    return distinct


def _reach(
    node: _Node, first: int, reached: dict[int, _Reach], unread: dict[int, int], steps: _Steps
) -> tuple[_Reach, int]:
    """What one list reaches, its own nodes numbered from ``first``, and the next free number.

    Each list it holds has its reach read once, and let go at its last read.
    """
    steps.spend(len(node))
    held = [part for part in node[1:] if isinstance(part, list)]
    own = len(node) - len(held)
    reach: _Reach = ((first, (1 << own) - 1),)
    for part in held:
        reach = _joined(reach, reached[id(part)], steps)
        unread[id(part)] -= 1
        if not unread[id(part)]:
            del reached[id(part)]
    steps.spend(sum(bits.bit_length() for _, bits in reach) // _BITS_PER_STEP)
    return reach, first + own


def _joined(reach: _Reach, other: _Reach, steps: _Steps) -> _Reach:
    """Two reaches as one: their runs in order, a run that overlaps or nears the last merged in.

    Runs that overlap share numbers, and merged they count each once. A step
    goes to each run, and to each `_BITS_PER_STEP` bits a merge writes.
    """
    steps.spend(len(reach) + len(other))
    runs: list[_Run] = []
    end = 0
    for low, bits in sorted(reach + other):
        if runs and low <= end + _GAP:
            start, merged = runs[-1]
            steps.spend((low - start + bits.bit_length()) // _BITS_PER_STEP)
            runs[-1] = (start, merged | (bits << (low - start)))
        else:
            runs.append((low, bits))
        end = max(end, low + bits.bit_length())
    return tuple(runs)
