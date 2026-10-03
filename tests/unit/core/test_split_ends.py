"""Which splits a fork reads counted back from the end of their list, which decides whether the
input's own count bounds a split's count (see ``solver.split_paths``)."""

import pytest

from pyct.core.branch import Expression
from pyct.core.str_splits import splits_read_from_the_end

LINES: Expression = ["splitlines", "s"]
PARTS: Expression = ["split", "s", "','"]

# a fork, and whether it reads the split's list from its end
FORKS: dict[str, tuple[Expression, bool]] = {
    "a negative index": (["==", ["[]", LINES, -1], "'z'"], True),
    "a negative slice start": ([">", ["len", ["[:]", LINES, -2, None]], 0], True),
    "a pop's slice": (["==", ["len", ["[:]", PARTS, None, -1]], 2], True),
    "a reverse": (["==", ["[]", ["[:]", PARTS, None, None, -1], 0], "'z'"], True),
    "a list joined to it, then a negative index": (
        ["==", ["[]", ["+", PARTS, ["[,]", "'z'"]], -2], "'y'"],
        True,
    ),
    "a read inside a compare": (["==", ["+", ["[]", PARTS, -1], "'!'"], "'z!'"], True),
    "an index from the start": (["==", ["[]", LINES, 0], "'z'"], False),
    "a slice from the start": (["!=", ["len", ["[:]", LINES, 1, None]], 0], False),
    "a length": ([">", ["len", LINES], "n"], False),
    "a negative number elsewhere": ([">", ["len", LINES], -1], False),
    "a negative index into a display of a piece": (
        ["==", ["[]", ["[,]", ["[]", PARTS, 0]], -1], "'z'"],
        False,
    ),
}


@pytest.mark.parametrize(("expression", "ended"), FORKS.values(), ids=list(FORKS))
def test_a_split_is_read_from_its_end_by_a_negative_position(
    expression: Expression, ended: bool
) -> None:
    found = splits_read_from_the_end(expression)

    assert bool(found) is ended
    assert all(part is LINES or part is PARTS for part in found), found


def test_a_list_changed_many_times_is_looked_at_once_per_part() -> None:
    form: Expression = PARTS
    for _ in range(200):
        # each change names the list before it twice, as a list changed in place does
        form = ["+", ["[:]", form, None, -1], ["[:]", form, 0, 1]]

    found = splits_read_from_the_end(["==", ["len", form], 3])

    assert found and all(part is PARTS for part in found)
