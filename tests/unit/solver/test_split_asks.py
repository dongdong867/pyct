"""A split's count on a path where it meets more than a plain int, as c*, and a piece read from
its end on many pieces, with cvc5 held against Python on each."""

import time
from typing import Any

import pytest

from pyct.binding.bind import Seed
from pyct.binding.model import apply
from pyct.core.branch import Expression
from pyct.core.str_splits import LONGEST_WALK
from pyct.solver.answer import Sat, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.lists import Origin
from pyct.solver.render import program
from tests.unit.solver.agreement import needs_cvc5
from tests.unit.solver.test_render import fork


def test_a_read_from_the_end_of_many_lines_writes_a_program_of_bounded_size() -> None:
    # read where the input's own count puts it, by two walks to it, so the program stays small
    lines: Expression = ["splitlines", "s"]
    path = (
        fork([">=", ["len", lines], 1], taken=True),
        fork(["==", ["[]", lines, -1], "'z'"], taken=True),
    )
    origin = Origin(values={"s": "a\n" * 300})

    text = program(path, {"s": str}, origin).text

    assert len(text) < 2_000_000, len(text)


@needs_cvc5
def test_a_count_a_tracked_int_meets_is_the_count_the_path_s_numbers_allow() -> None:
    parts: Expression = ["split", "s", "','"]
    path = (
        fork(["<", ["len", parts], 20], taken=False),
        fork(["==", ["len", parts], "n"], taken=True),
    )
    args = Seed.of({"s": "a", "n": 0})

    answer = solve(path, args.leaves, 10.0, args.lists, args.values)

    # the count n meets is c*: twenty, the count nearest the input's one piece that the fork
    # on the count with 20 allows, and that fork holds the string to twenty pieces or more
    assert isinstance(answer, Sat), answer
    values = dict(apply(args, answer.model).args)
    count = len(str(values["s"]).split(","))
    assert count >= 20 and values["n"] == 20, values


@needs_cvc5
def test_an_unrelated_number_on_the_path_leaves_a_count_s_flip_quick() -> None:
    split: Expression = ["split", "s", "','"]
    path = (
        fork([">", "x", 1000], taken=True),
        fork(["==", ["len", split], ["+", "m", 1]], taken=True),
    )
    seed = Seed.of({"s": "a", "x": 0, "m": 5})

    started = time.perf_counter()
    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    assert isinstance(answer, Sat), answer
    assert time.perf_counter() - started < 3.0
    args = dict(apply(seed, answer.model).args)
    s, x, m = str(args["s"]), args["x"], args["m"]
    assert isinstance(x, int) and isinstance(m, int), args
    assert x > 1000 and len(s.split(",")) == m + 1, args


@needs_cvc5
@pytest.mark.parametrize(
    "guard",
    [["<", ["len", "s"], 100], [">", ["len", ["split", "t", "','"]], 1000]],
    ids=["a string's length", "a large count of another split"],
)
def test_a_length_guard_leaves_a_split_s_flip_quick(guard: list[Expression]) -> None:
    split: Expression = ["split", "s", "','"]
    path = (
        fork(guard, taken=guard[0] == "<"),
        fork(["==", ["len", split], ["+", "m", 1]], taken=True),
        fork(["==", ["[]", split, 0], "'x'"], taken=True),
    )
    seed = Seed.of({"s": "a", "t": "b", "m": 5})

    started = time.perf_counter()
    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # a string's length says nothing of the pieces, and a count past 1,000 is one membership
    assert isinstance(answer, Sat), answer
    assert time.perf_counter() - started < 3.0
    args = dict(apply(seed, answer.model).args)
    s, t, m = str(args["s"]), str(args["t"]), args["m"]
    assert isinstance(m, int) and len(s.split(",")) == m + 1 and s.split(",")[0] == "x", args
    assert len(s) < 100 if guard[0] == "<" else len(t.split(",")) <= 1000, args


@needs_cvc5
def test_the_last_of_many_lines_is_read_where_the_input_s_count_puts_it() -> None:
    lines: Expression = ["splitlines", "s"]
    path = (
        fork([">=", ["len", lines], 1], taken=True),
        fork(["==", ["[]", lines, -1], "'z'"], taken=True),
    )
    seed = Seed.of({"s": "a\n" * 12})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # chosen among every count up to 14 this ran past the limit; read where the input's own
    # twelve lines put it, cvc5 answers
    assert isinstance(answer, Sat), answer
    assert str(apply(seed, answer.model).args["s"]).splitlines()[-1] == "z"


@needs_cvc5
@pytest.mark.parametrize("count", [7, 8])
def test_the_last_of_several_lines_is_flipped(count: int) -> None:
    lines: Expression = ["splitlines", "s"]
    path = (
        fork([">=", ["len", lines], 1], taken=True),
        fork(["==", ["[]", lines, -1], "'end'"], taken=True),
    )
    seed = Seed.of({"s": "a\n" * (count - 1) + "x"})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # read first where the input's own count puts the last line, which answers
    assert isinstance(answer, Sat), answer
    assert str(apply(seed, answer.model).args["s"]).splitlines()[-1] == "end"


@needs_cvc5
def test_a_slice_s_length_counts_the_pieces_it_leaves_out() -> None:
    parts: Expression = ["split", "s", "','"]
    path = (fork([">", ["len", ["[:]", parts, 2, None]], 3], taken=True),)
    seed = Seed.of({"s": "a"})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # six pieces, two of them before the slice: the bound counts the two
    assert isinstance(answer, Sat), answer
    text = str(apply(seed, answer.model).args["s"])
    assert len(text.split(",")[2:]) > 3, text


@needs_cvc5
def test_an_rsplit_past_the_walk_counts_its_pieces_on_any_string() -> None:
    parts: Expression = ["rsplit", "s", "','", LONGEST_WALK + 1]
    path = (
        fork([">", ["len", parts], 2], taken=False),
        fork(["in", "',,,'", "s"], taken=True),
    )
    seed = Seed.of({"s": "a"})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # three commas make four pieces, so no string takes both; the string the pieces are read
    # on is the reads' restriction, not the count's, and does not free it
    assert isinstance(answer, Unsat), answer


# a separator split read from its end: the split, the input's string, and whether the path then
# asks the count to meet a tracked int
FROM_THE_END: dict[str, tuple[Expression, str, bool]] = {
    "the last of five pieces, limited": (["split", "s", "','", 20], "a,a,a,a,x", False),
    "the last of eight pieces, limited, then a count": (
        ["split", "s", "','", 20],
        "a,b,c,d,e,f,g,end",
        True,
    ),
    "the last of seven pieces on a separator that overlaps itself, then a count": (
        ["split", "s", "'--'"],
        "a--b--c--d--e--f--end",
        True,
    ),
    "the last of nine pieces, limited, then a count": (
        ["split", "s", "','", 20],
        ",".join(["a"] * 8 + ["end"]),
        True,
    ),
    "the last of twelve pieces on a separator that overlaps itself, then a count": (
        ["split", "s", "'--'"],
        "--".join(["a"] * 11 + ["end"]),
        True,
    ),
    "the last of eighteen pieces, limited": (["split", "s", "','", 20], "a," * 17 + "x", False),
    "the last of twenty-five pieces, limited past them": (
        ["split", "s", "','", 20],
        "a," * 24 + "x",
        False,
    ),
}


@needs_cvc5
@pytest.mark.parametrize(
    ("split", "text", "counted"), FROM_THE_END.values(), ids=list(FROM_THE_END)
)
def test_a_piece_from_the_end_of_a_separator_split_is_answered(
    split: list[Expression], text: str, counted: bool
) -> None:
    path = [
        fork([">=", ["len", split], 1], taken=True),
        fork(["==", ["[]", split, -1], "'end'"], taken=True),
    ]
    if counted:
        path.append(fork(["==", ["len", split], "n"], taken=True))
    seed = Seed.of({"s": text, "n": 0})

    answer = solve(tuple(path), seed.leaves, 10.0, seed.lists, seed.values)

    # read where the input's own count puts it, and a count tied by one replace term
    assert isinstance(answer, Sat), answer
    args = apply(seed, answer.model).args
    operands: list[Any] = [part[1:-1] if isinstance(part, str) else part for part in split[2:]]
    pieces = str(args["s"]).split(*operands)
    assert pieces[-1] == "end", args
    assert not counted or len(pieces) == args["n"], args


@needs_cvc5
def test_a_limited_count_that_meets_a_term_holds_no_separators_past_the_limit() -> None:
    parts: Expression = ["split", "s", "','", 1]
    path = (
        fork(["==", ["len", parts], "n"], taken=True),
        fork(["==", ["[]", parts, 1], "'b,c,d,e'"], taken=True),
    )
    seed = Seed.of({"s": "a,b", "n": 0})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # the limit keeps the count at two however many commas the rest holds
    assert isinstance(answer, Sat), answer
    args = apply(seed, answer.model).args
    pieces = str(args["s"]).split(",", 1)
    assert len(pieces) == args["n"] and pieces[1] == "b,c,d,e", args


# a count that meets a tracked int with no read from the end, on an input with many pieces
MANY_PIECES: dict[str, tuple[Expression, str]] = {
    "seventeen lines": (["splitlines", "s"], "a\n" * 16 + "x"),
    "twenty-four pieces on a separator that overlaps itself": (
        ["split", "s", "'--'"],
        "--".join(["a"] * 24),
    ),
}


@needs_cvc5
@pytest.mark.parametrize(("split", "text"), MANY_PIECES.values(), ids=list(MANY_PIECES))
def test_a_count_of_many_pieces_that_meets_a_term_is_answered(
    split: list[Expression], text: str
) -> None:
    path = (fork(["==", ["len", split], "n"], taken=True),)
    seed = Seed.of({"s": text, "n": 0})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # the count is the input's own, held, where a tie of that many walks ran past the limit
    assert isinstance(answer, Sat), answer
    args = apply(seed, answer.model).args
    operands: list[Any] = [part[1:-1] if isinstance(part, str) else part for part in split[2:]]
    assert len(getattr(str(args["s"]), str(split[0]))(*operands)) == args["n"], args


@needs_cvc5
@pytest.mark.parametrize(
    ("number", "taken"), [(10, False), (7, True)], ids=["at most ten", "more than seven"]
)
def test_the_last_line_is_read_at_the_count_the_forks_allow_nearest_the_input_s(
    number: int, taken: bool
) -> None:
    lines: Expression = ["splitlines", "s"]
    path = (
        fork([">=", ["len", lines], 1], taken=True),
        fork(["==", ["[]", lines, -1], "'end'"], taken=True),
        fork([">", ["len", lines], number], taken=taken),
    )
    seed = Seed.of({"s": "a\n" * 11 + "x"})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # twelve lines, moved to ten or kept, where a count walked beside the last line ran past
    # the limit
    assert isinstance(answer, Sat), answer
    text = str(apply(seed, answer.model).args["s"]).splitlines()
    assert text[-1] == "end" and (len(text) > number) is taken, text


_LINES: Expression = ["splitlines", "s"]
_REST: Expression = ["[:]", _LINES, 1, None]


@needs_cvc5
@pytest.mark.parametrize("count", [12, 16, 17])
def test_the_first_of_the_rest_of_many_lines_is_flipped(count: int) -> None:
    path = (
        fork(["!=", ["len", _REST], 0], taken=True),
        fork([">", ["len", _REST], 0], taken=True),
        fork(["==", ["[]", _REST, 0], "'end'"], taken=True),
    )
    seed = Seed.of({"s": "a\n" * (count - 1) + "x"})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # the slice's clamp names the count, which no read from the end bounds by the input's own
    # lines: tied to each of them it ran past the limit at 12 and kept the string past 16
    assert isinstance(answer, Sat), answer
    lines = str(apply(seed, answer.model).args["s"]).splitlines()
    assert lines[1:] and lines[1:][0] == "end", lines


@needs_cvc5
@pytest.mark.parametrize("count", [12, 16, 17])
def test_the_first_of_many_lines_past_a_tracked_count_is_flipped(count: int) -> None:
    path = (
        fork([">", ["len", _LINES], "n"], taken=True),
        fork([">", ["len", _LINES], 0], taken=True),
        fork(["==", ["[]", _LINES, 0], "'end'"], taken=True),
    )
    seed = Seed.of({"s": "a\n" * (count - 1) + "x", "n": 0})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # the count meets a tracked int, and nothing reads the lines from their end
    assert isinstance(answer, Sat), answer
    args = apply(seed, answer.model).args
    lines, n = str(args["s"]).splitlines(), args["n"]
    assert isinstance(n, int) and lines[0] == "end" and len(lines) > n, args
