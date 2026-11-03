"""What a path found unsat is answered when a read of it may land on an item of another kind.

A read says the kind Python read (``core.branch.READ_HEADS``), and the program holds it to that
kind: where its position lands, the item is of that kind. That is all a sat answer needs. An unsat
says less, since another input's index may land on another kind, `g[i][0] > 3.0 and i == 0` with
`g=[[1],[0.5]]` at `i=1`. So an unsat is the path's only once each kind each such read may take was
asked. A read that may land on a kind no ask can write, a str, a None or a list, leaves it an
``Unknown()``, and so do more asks than ``KIND_ASKS``.
"""

from collections.abc import Callable, Iterable, Mapping, Sequence
from itertools import islice, product

from pyct.solver.answer import Answer, Sat, Timeout, Unknown, Unsat

# the most asks one unsat takes with other kinds of read. One read of a list of three kinds of
# number takes two, and three reads take 26, so at most two such reads are asked at once
KIND_ASKS = 8

# which read takes which kind: by its place among the reads that may move (``ListTyping``)
type ReadKinds = Mapping[int, str]


def assignments(others: Sequence[frozenset[str]]) -> Iterable[ReadKinds] | None:
    """Each way the reads that may move take another kind, the fewest reads changed first; None
    when there are more of them than ``KIND_ASKS``."""
    count = 1
    for kinds in others:
        count *= len(kinds) + 1
    if count - 1 > KIND_ASKS:
        return None
    choices = [(None, *sorted(kinds)) for kinds in others]
    made = (
        {at: kind for at, kind in enumerate(picked) if kind is not None}
        for picked in product(*choices)
    )
    return sorted(islice(made, 1, None), key=len)


def asked_of_each(
    others: Sequence[frozenset[str]], untried: bool, ask: Callable[[ReadKinds], Answer]
) -> Answer:
    """What an unsat with each read at the kind Python read comes to, asking each other kind:
    the first sat, an ``Unsat()`` when every kind was asked and answered so, a ``Timeout()`` when
    time ran out on an ask, and an ``Unknown()`` for any other outcome."""
    if not others and not untried:
        return Unsat()
    each = assignments(others)
    if each is None:
        return Unknown()
    proved = not untried
    for kinds in each:
        answer = ask(kinds)
        if isinstance(answer, Sat | Timeout):
            return answer
        proved = proved and isinstance(answer, Unsat)
    return Unsat() if proved else Unknown()
