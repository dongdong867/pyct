"""Acceptance tests for sizes that start small and grow (plan nested-floats-bools, 5.8).

A float's int as a list's index leaves the list's length to cvc5, which picks the top of its
bound: a list of a million items, which takes most of a short budget to build and run. Each
size the solver chooses is held small on the first ask, so the answer is short and the line it
reaches is covered within the budget.
"""

import pytest

from tests.acceptance.test_nested_floats_and_bools import (
    args_of,
    lines_of,
    missing_lines,
    solved,
)

NESTED = "targets.nested.floats_and_bools::float_as_int_indexes"
PLAIN = "targets.lists.float_index::float_indexes"


@pytest.mark.parametrize(
    ("target", "seed"),
    [(NESTED, {"ys": [0, 1, 2], "xs": [1.5]}), (PLAIN, {"ys": [0, 1, 2], "x": 1.5})],
    ids=["float-inside-a-list", "float-parameter"],
)
def test_a_float_s_int_as_an_index_answers_a_short_list_within_the_budget(
    target: str, seed: dict[str, object]
) -> None:
    lines = lines_of(target, seed, "--budget", "4")

    assert missing_lines(target, lines) == set()
    answers = solved(lines)
    assert answers
    # the seed holds 3 items: the first ask holds an answer to 2 * 3 + 8
    assert all(len(args_of(line, "ys")) <= 14 for line in answers)
