"""A split's list read through tracked or other operands it does not follow: list's own
answer, as origin/v2's plain list of pieces gives it, each piece kept, and a piece a tracked
operand handed out pinned to the operand's value (keep-a-tracked-index-into-a-split-as-v2-does)."""

from typing import Any

import pytest

from pyct.core.branch import Branch, Downgrade, Expression, SinkItem
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr

SPLIT: Expression = ["split", "s", "','"]


def _split_of_four(sink: list[SinkItem]) -> Any:
    return ConcolicStr.made("a,b,c,d", expression="s", sink=sink).split(",")


def _walks(sink: list[SinkItem]) -> list[Expression]:
    return [item.expression for item in sink if isinstance(item, Branch)]


@pytest.mark.parametrize(
    ("read", "answer"),
    [
        (lambda parts, n: parts[n], "b"),
        (lambda parts, n: parts[-n], "d"),
        (lambda parts, n: parts[::2], ["a", "c"]),
        (lambda parts, n: parts * n, ["a", "b", "c", "d"]),
        (lambda parts, n: parts.index("c", n), 2),
        (lambda parts, n: parts.index("c", 1), 2),
    ],
    ids=[
        *("an index", "an index from the end", "a step of 2", "a repeat"),
        *("a search from a tracked start", "a search from a plain start"),
    ],
)
def test_list_s_own_answer_on_a_split_s_list_keeps_its_pieces(read: Any, answer: object) -> None:
    sink: list[SinkItem] = []
    parts = _split_of_four(sink)
    n = ConcolicInt.made(1, expression="n", sink=sink)
    sink.clear()

    got = read(parts, n)

    # as origin/v2's plain list of pieces answers: each piece keeps its condition, and no loss
    # is named
    assert got == answer
    assert [item for item in sink if isinstance(item, Downgrade)] == [], sink
    pieces = got if isinstance(got, list) else [got]
    assert all(type(piece) is ConcolicStr for piece in pieces if isinstance(piece, str))
    assert parts.expression == SPLIT


@pytest.mark.parametrize(
    ("read", "written"),
    [
        (lambda parts, n: [parts[n]], [["pin", 1, "n", 1]]),
        (lambda parts, n: [parts[-n]], [["pin", -1, ["-", "n"], -1]]),
        (lambda parts, n: parts[n:][:1], [["pin", 1, "n", 1]]),
        (lambda parts, n: (parts * n)[:1], [["pin", 0, "n", 1]]),
        (lambda parts, n: [parts[::2][0]], [0]),
    ],
    ids=["an index", "an index from the end", "a cut", "a repeat", "plain operands"],
)
def test_a_piece_handed_out_through_a_tracked_operand_is_pinned_to_its_value(
    read: Any, written: list[Expression]
) -> None:
    sink: list[SinkItem] = []
    parts = _split_of_four(sink)
    n = ConcolicInt.made(1, expression="n", sink=sink)

    pieces = read(parts, n)

    # the piece is read at its own position, or from the end where Python read it from the end
    # of the split's own list, only while each tracked operand has its value
    assert [piece.expression[2] for piece in pieces] == written


def test_a_search_from_a_tracked_start_compares_pinned_pieces() -> None:
    sink: list[SinkItem] = []
    parts = _split_of_four(sink)
    n = ConcolicInt.made(1, expression="n", sink=sink)
    sink.clear()

    parts.index("c", n)

    split = ["split", "s", "','"]
    assert _walks(sink) == [["==", ["[]", split, ["pin", at, "n", 1]], "'c'"] for at in (1, 2)], (
        sink
    )
