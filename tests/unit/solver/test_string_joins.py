"""A join of strings in SMT-LIB: the concatenation it is, the items a tracked list's walk says it
holds, and each split it reads held to its number of pieces, with cvc5 held against Python."""

import pytest

from pyct.binding.bind import Seed
from pyct.core.branch import Branch, Expression
from pyct.solver.answer import Sat, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.splits import COUNTED
from pyct.solver.str_joins import counted, expanded
from tests.unit.solver.agreement import needs_cvc5
from tests.unit.solver.test_render_lists import answered, fork

SPLIT: Expression = ["split", "s", "','"]
PIECES: Expression = ["[,]", ["[]", SPLIT, 0], ["[]", SPLIT, 1]]


def _names(_part: Expression) -> bool:
    return False


def _expressions(prefix: tuple[Branch, ...]) -> list[Expression]:
    return [branch.expression for branch in expanded(prefix, _names)]


def _walk(name: Expression, count: int) -> list[Branch]:
    """The forks a join's walk of a tracked list records: one per item, and one where it ends."""
    return [fork([">", ["len", name], at], taken=at < count) for at in range(count + 1)]


def test_a_path_with_no_join_is_handed_back_as_it_is() -> None:
    prefix = (fork(["==", "s", "'a'"]),)

    assert expanded(prefix, _names) is prefix


@pytest.mark.parametrize(
    ("items", "written"),
    [
        ([], "''"),
        (["a"], "a"),
        (["a", ["upper", "b"], "'c'"], ["+", "a", "'-'", ["upper", "b"], "'-'", "'c'"]),
    ],
    ids=["none", "one", "three"],
)
def test_a_join_of_a_display_is_its_items_with_the_separator_between(
    items: list[Expression], written: Expression
) -> None:
    joined: Expression = ["join", "'-'", ["[,]", *items]]

    assert _expressions((fork(["==", joined, "'x'"]),)) == [["==", written, "'x'"]]


def test_a_join_of_a_tracked_list_reads_as_many_items_as_its_walk_ended_on() -> None:
    changed: Expression = ["+", "parts", ["[,]", "x"]]
    joined: Expression = ["join", "sep", changed]

    written = _expressions((*_walk(changed, 2), fork(["==", joined, "'a'"])))

    items = [["[]", changed, 0], "sep", ["[]", changed, 1]]
    assert written[-1] == ["==", ["+", *items], "'a'"]


def test_a_join_of_a_tracked_list_no_walk_ended_on_is_a_pyct_bug() -> None:
    with pytest.raises(ValueError, match="no walk ends on it"):
        expanded((fork(["==", ["join", "'-'", "parts"], "'a'"]),), _names)


def test_each_split_a_join_reads_is_held_to_one_more_piece_than_the_path_reads() -> None:
    later = fork(["==", ["[]", SPLIT, 2], "'z'"], taken=False)

    written = _expressions((fork(["==", ["join", "'-'", PIECES], "'a-b'"]), later))

    assert written[-1] == [COUNTED, SPLIT, 3]


@pytest.mark.parametrize(
    ("head", "operands", "count"),
    [("partition", ("','",), 3), ("split", ("','", 1), 2), ("rsplit", (None, 0), 1)],
    ids=["partition", "split at its limit", "rsplit at its limit"],
)
def test_a_split_that_cannot_hold_more_pieces_needs_no_hold(
    head: str, operands: tuple[Expression, ...], count: int
) -> None:
    split: Expression = [head, "s", *operands]

    assert counted(split, "s", count) == "true"


@needs_cvc5
def test_cvc5_joins_a_tracked_list_as_python_does() -> None:
    joined: Expression = ["join", "'-'", "parts"]
    args = answered({"parts": ["x", "y"]}, *_walk("parts", 2), fork(["==", joined, "'a-b'"]))

    parts = args["parts"]
    assert isinstance(parts, list) and "-".join(parts) == "a-b"


@needs_cvc5
def test_cvc5_answers_no_split_with_more_pieces_than_the_join_reads() -> None:
    joined = fork(["==", ["join", "'-'", PIECES], "'a-b'"])
    seed = Seed.of({"s": "x,y"})

    held = solve((joined,), seed.leaves, 10.0)
    more = solve((joined, fork([">=", ["count", "s", "','"], 2])), seed.leaves, 10.0)

    # Python joins every piece: a string with one comma more joins three
    assert isinstance(held, Sat) and "-".join(str(held.model["s"]).split(",")) == "a-b"
    assert isinstance(more, Unsat)
