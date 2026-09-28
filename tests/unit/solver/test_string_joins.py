"""A join of strings in SMT-LIB: the concatenation it is, and the items a tracked list's walk,
a split's among them, says it holds, with cvc5 held against Python."""

import pytest

from pyct.binding.bind import Seed
from pyct.core.branch import Branch, Expression
from pyct.solver.answer import Sat, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.str_joins import expanded
from tests.unit.solver.agreement import needs_cvc5
from tests.unit.solver.test_render_lists import answered, fork

SPLIT: Expression = ["split", "s", "','"]


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


def test_a_join_of_a_split_reads_as_many_pieces_as_its_walk_ended_on() -> None:
    joined: Expression = ["join", "'-'", SPLIT]

    written = _expressions((*_walk(SPLIT, 2), fork(["==", joined, "'a'"])))

    items = [["[]", SPLIT, 0], "'-'", ["[]", SPLIT, 1]]
    assert written[-1] == ["==", ["+", *items], "'a'"]


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
def test_cvc5_answers_no_split_with_more_pieces_than_its_walk_ended_on(
    split: list[Expression], seed: str, more: Expression
) -> None:
    joined = fork(["==", ["join", "'-'", split], "'a-b'"])
    path = (*_walk(split, 2), joined)
    args = Seed.of({"s": seed})

    kept = solve(path, args.leaves, 10.0, args.lists, args.values)
    another = solve((*path, fork(more)), args.leaves, 10.0, args.lists, args.values)

    # the walk's last fork says the split has two pieces: a string with one more is no answer
    assert isinstance(kept, Sat), kept
    text = str(kept.model["s"])
    head, *operands = [split[0], *(_plain(part) for part in split[2:])]
    assert "-".join(getattr(str, str(head))(text, *operands)) == "a-b", text
    assert isinstance(another, Unsat), another


def _plain(part: Expression) -> object:
    """A split's plain operand as Python takes it: a literal's text, or the number."""
    return part[1:-1] if isinstance(part, str) else part
