"""Which letters of a string a path spells out: dense reads from position zero, and no more."""

import pytest

from pyct.core.branch import Expression
from pyct.solver.letters import furthest_reads


def _named(part: Expression) -> str | None:
    """The one string here is the leaf s."""
    return part if part == "s" else None


def _furthest(positions: list[int]) -> int | None:
    order: list[list[Expression]] = [["[]", "s", at] for at in positions]
    return furthest_reads(order, _named).get("s")


# the positions a path reads, and the last letter it spells, None for none
READS: dict[str, tuple[list[int], int | None]] = {
    "a walk": (list(range(40)), 39),
    "every other letter": ([0, 2, 4, 6], 6),
    "one read": ([5], None),
    "two reads far apart": ([0, 20_000], None),
    "a walk, then a read far off": ([0, 1, 2, 20_000], 2),
    "a negative index": ([0, -1], None),
}


@pytest.mark.parametrize(("positions", "last"), READS.values(), ids=list(READS))
def test_only_dense_reads_are_spelled(positions: list[int], last: int | None) -> None:
    assert _furthest(positions) == last


@pytest.mark.parametrize("positions", [p for p, _ in READS.values()], ids=list(READS))
def test_the_letters_are_never_more_than_twice_the_reads(positions: list[int]) -> None:
    last = _furthest(positions)

    assert last is None or last + 1 <= 2 * len(positions)
