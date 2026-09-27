"""A join of strings in SMT-LIB: the concatenation it is, the items a tracked list's walk says it
holds, and each split it reads held to its number of pieces, with cvc5 held against Python."""

from collections.abc import Callable

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
PIECE_ITEMS: list[Expression] = [["[]", SPLIT, 0], ["[]", SPLIT, 1]]
PIECES: Expression = ["[,]", *PIECE_ITEMS]


def _names(_part: Expression) -> bool:
    return False


def _held(values: dict[str, object]) -> Callable[[Expression], object]:
    """What the input holds for a parameter the part names, as render reads the input."""
    return lambda part: values.get(part) if isinstance(part, str) else None


def _expressions(prefix: tuple[Branch, ...], **values: object) -> list[Expression]:
    return [branch.expression for branch in expanded(prefix, _names, _held(values))]


def _walk(name: Expression, count: int) -> list[Branch]:
    """The forks a join's walk of a tracked list records: one per item, and one where it ends."""
    return [fork([">", ["len", name], at], taken=at < count) for at in range(count + 1)]


def test_a_path_with_no_join_is_handed_back_as_it_is() -> None:
    prefix = (fork(["==", "s", "'a'"]),)

    assert expanded(prefix, _names, _held({})) is prefix


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
        expanded((fork(["==", ["join", "'-'", "parts"], "'a'"]),), _names, _held({}))


@pytest.mark.parametrize(
    "items",
    [PIECE_ITEMS, [["upper", ["[]", SPLIT, 1]], ["upper", ["[]", SPLIT, 0]]]],
    ids=["as they are", "through an operation"],
)
def test_a_split_whose_every_piece_a_join_reads_is_held_to_its_number(
    items: list[Expression],
) -> None:
    written = _expressions((fork(["==", ["join", "'-'", ["[,]", *items]], "'a-b'"]),), s="x,y")

    assert written[-1] == [COUNTED, SPLIT, 2]


@pytest.mark.parametrize(
    ("joined", "s"),
    [
        # part of the list: the input's split has three pieces, and the join reads two
        (PIECES, "x,y,z"),
        # a split read only as the string of another split
        (["[,]", ["[]", ["split", ["[]", SPLIT, 0], "':'"], 0]], "x:y,z"),
        # a split of a string the input does not hold as it is
        (["[,]", ["[]", ["split", ["upper", "s"], "','"], 0]], "x"),
    ],
    ids=["part of the list", "through another split", "of a changed string"],
)
def test_any_other_split_a_join_reads_is_left_free(joined: Expression, s: str) -> None:
    written = _expressions((fork(["==", ["join", "'-'", joined], "'a'"]),), s=s)

    assert len(written) == 1


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
@pytest.mark.parametrize(
    ("split", "seed", "more"),
    [
        (SPLIT, "x,y", [">=", ["count", "s", "','"], 2]),
        (["rsplit", "s", "','", 3], "x,y", [">=", ["count", "s", "','"], 2]),
        (["splitlines", "s"], "x\ny", [">=", ["count", "s", "'\\n'"], 3]),
    ],
    ids=["split", "rsplit with a limit", "splitlines"],
)
def test_cvc5_answers_no_split_with_more_pieces_than_the_join_reads(
    split: list[Expression], seed: str, more: Expression
) -> None:
    pieces: Expression = ["[,]", ["[]", split, 0], ["[]", split, 1]]
    joined = fork(["==", ["join", "'-'", pieces], "'a-b'"])
    args = Seed.of({"s": seed})

    held = solve((joined,), args.leaves, 10.0, args.lists, args.values)
    another = solve((joined, fork(more)), args.leaves, 10.0, args.lists, args.values)

    # Python joins every piece: a string with one piece more joins three
    assert isinstance(held, Sat), held
    text = str(held.model["s"])
    head, *operands = [split[0], *(_plain(part) for part in split[2:])]
    assert "-".join(getattr(str, str(head))(text, *operands)) == "a-b", text
    assert isinstance(another, Unsat), another


def _plain(part: Expression) -> object:
    """A split's plain operand as Python takes it: a literal's text, or the number."""
    return part[1:-1] if isinstance(part, str) else part


def test_a_count_of_anything_but_a_split_is_a_pyct_bug() -> None:
    with pytest.raises(ValueError, match="the solver writes a split"):
        counted("s", "s", 2)
