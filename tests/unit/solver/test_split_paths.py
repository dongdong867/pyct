"""The splits of one path as the program writes them: the count a read from the end puts its
piece at, which the forks on a split's own length narrow, and the tie that says what a count
is."""

import pytest

from pyct.core.branch import Expression
from pyct.solver.split_lists import SplitList
from pyct.solver.split_paths import Splits
from tests.unit.solver.test_render import fork

PARTS: list[Expression] = ["split", "s", "','"]
LENGTH: Expression = ["len", PARTS]
# the input's string, with twelve pieces
TWELVE = ",".join("a" * 12)

# the forks on the split's length, each with the side taken, and the count a read from the end
# of twelve pieces is read at
RANGES: dict[str, tuple[list[tuple[Expression, bool]], int]] = {
    "more than, taken": ([([">", LENGTH, 20], True)], 21),
    "at least, taken": ([([">=", LENGTH, 15], True)], 15),
    "fewer than, taken": ([(["<", LENGTH, 5], True)], 4),
    "at most, taken": ([(["<=", LENGTH, 5], True)], 5),
    "equal, taken": ([(["==", LENGTH, 7], True)], 7),
    "more than, not taken": ([([">", LENGTH, 5], False)], 5),
    "at least, not taken": ([([">=", LENGTH, 5], False)], 4),
    "fewer than, not taken": ([(["<", LENGTH, 15], False)], 15),
    "at most, not taken": ([(["<=", LENGTH, 15], False)], 16),
    "not equal, not taken": ([(["!=", LENGTH, 7], False)], 7),
    "not equal, taken": ([(["!=", LENGTH, 7], True)], 12),
    "equal, not taken": ([(["==", LENGTH, 7], False)], 12),
    "a number fewer than it": ([(["<", 20, LENGTH], True)], 21),
    "a number at most it": ([(["<=", 15, LENGTH], True)], 15),
    "a number more than it": ([([">", 5, LENGTH], True)], 4),
    "a number at least it": ([([">=", 5, LENGTH], True)], 5),
    "a number equal to it": ([(["==", 7, LENGTH], True)], 7),
    "a number not equal to it, not taken": ([(["!=", 7, LENGTH], False)], 7),
    "two forks between": ([([">", LENGTH, 3], True), (["<", LENGTH, 6], True)], 5),
    "a length the forks leave alone": ([([">", LENGTH, 3], True)], 12),
}


@pytest.mark.parametrize(("forks", "count"), RANGES.values(), ids=list(RANGES))
def test_a_read_from_the_end_is_put_at_the_count_the_forks_allow_nearest_the_input_s(
    forks: list[tuple[Expression, bool]], count: int
) -> None:
    splits = Splits()
    splits.given = lambda part: TWELVE if part == "s" else None
    splits.learn(tuple(fork(expression, taken=taken) for expression, taken in forks))

    listed = splits.made(PARTS, "s")

    assert listed.input_count == 12
    assert listed.read_count == count


def _listed(
    head: str, operands: tuple[object, ...], text: str, read_count: int | None = None
) -> SplitList:
    """A split's list of ``text`` held to the input's count, its bound two past it, and read
    from the end at ``read_count``, the input's own count unless given."""
    count = len(getattr(str, head)(text, *operands))
    read = count if read_count is None else read_count
    return SplitList(
        "s", head, operands, "c", count + 2, input_count=count, input_text=text, read_count=read
    )


@pytest.mark.parametrize(
    ("limit", "held"), [(3, False), (20, True), (None, True)], ids=["under", "past", "none"]
)
def test_a_replace_count_is_held_to_the_bound_only_where_no_limit_keeps_it_under(
    limit: int | None, held: bool
) -> None:
    operands = (",",) if limit is None else (",", limit)
    listed = SplitList("s", "split", operands, "c", 10)

    tie, holds = listed.tie(read_from_the_end=True)

    assert holds is held
    assert len(tie) == (2 if held else 1), tie
    assert "str.replace_all" in tie[0]


def test_a_count_of_many_lines_is_held_to_the_input_s_own_string() -> None:
    text = "a\n" * 16 + "x"

    tie, holds = _listed("splitlines", (), text).tie()

    assert holds is True
    assert tie == ["(assert (= c 17))", '(assert (= s "' + text.replace("\n", "\\u{a}") + '"))']


def test_a_count_the_forks_move_is_tied_by_walks_not_held_to_the_input_s() -> None:
    tie, holds = _listed("splitlines", (), "a\n" * 16 + "x", read_count=16).tie()

    assert holds is True
    assert "(assert (= c 17))" not in tie
    assert tie[0].startswith("(assert (= c (+ "), tie[0]


def test_a_count_of_many_pieces_on_a_separator_holds_only_their_number() -> None:
    text = "--".join("a" * 24)

    tie, holds = _listed("split", ("--",), text).tie()

    # one membership for each side of the count, and the string free to change
    assert holds is True
    assert tie[0] == "(assert (= c 24))"
    assert tie[1].count("str.in_re") == 2 and '"a--' not in tie[1], tie[1]


@pytest.mark.parametrize(("lines", "pinned"), [(14, False), (15, True)], ids=["14", "15"])
def test_a_count_is_held_to_the_input_s_own_once_its_bound_passes_sixteen(
    lines: int, pinned: bool
) -> None:
    tie, _ = _listed("splitlines", (), "a\n" * (lines - 1) + "x").tie()

    assert (f"(assert (= c {lines}))" in tie) is pinned, tie
