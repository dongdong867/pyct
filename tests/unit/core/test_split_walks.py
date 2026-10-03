"""A walk over a split's list marks its forks, which the tree aims at after the path's other
forks (fork-order-a-split-s-walk-forks-after-the-path-s-other-forks)."""

from typing import Any

import pytest

from pyct.core.branch import Branch, Expression, SinkItem
from pyct.core.str_splits import a_split_s_list
from pyct.core.strs import ConcolicStr
from tests.unit.core.test_list_reads import tracked


def _split(sink: list[SinkItem]) -> Any:
    return ConcolicStr.made("a,b", expression="s", sink=sink).split(",")


@pytest.mark.parametrize(
    ("made", "marked"),
    [
        (lambda sink: ConcolicStr.made("a\nb", expression="s", sink=sink).splitlines(), True),
        (lambda sink: _split(sink)[1:], True),
        (lambda sink: tracked(["a", "b"])[0], False),
    ],
    ids=["a split's list", "a slice of one", "an argument's list"],
)
def test_a_walk_over_a_split_s_list_marks_its_forks(made: Any, marked: bool) -> None:
    sink: list[SinkItem] = []
    items = made(sink)
    sink = sink or items.sink

    list(items)
    walks = [item for item in sink if isinstance(item, Branch) and item.lost_as == "__iter__"]

    # a list argument's walk keeps the order it had
    assert walks and all(branch.split_walk is marked for branch in walks), walks


SPLIT: Expression = ["split", "s", "','"]


@pytest.mark.parametrize(
    ("form", "marked"),
    [
        (SPLIT, True),
        (["[:]", SPLIT, 1, None], True),
        (["*", SPLIT, 2], True),
        (["+", SPLIT, ["[,]", "'z'"]], True),
        (["+", ["[,]", "'z'"], ["[:]", SPLIT, None, -1]], True),
        (["+", SPLIT, "xs"], False),
        (["+", "xs", SPLIT], False),
        ("xs", False),
    ],
    ids=[
        "its own",
        "a slice",
        "a repeat",
        "appended to",
        "joined on a display",
        "joined",
        "joined on",
        "an argument",
    ],
)
def test_a_split_s_list_is_one_whose_items_are_its_pieces_or_the_target_s(
    form: Expression, marked: bool
) -> None:
    # a list joined with another list, an argument's say, keeps a list argument's order, and
    # its inputs are let go as v2 lets them go
    assert a_split_s_list(form) is marked
