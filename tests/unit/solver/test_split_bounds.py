"""A split's bound on a path: how many pieces a count is tied to, the input's own count, and the
loosened ask past the bound, with cvc5 held against Python on each."""

import time
from typing import Any

import pytest

from pyct.binding.bind import Seed
from pyct.binding.model import apply
from pyct.core.branch import Expression
from pyct.core.str_splits import LONGEST_WALK
from pyct.solver import cvc5 as cvc5_module
from pyct.solver.answer import Sat, Unknown, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.declared import Program
from pyct.solver.lists import Origin
from pyct.solver.render import program
from tests.unit.solver.agreement import needs_cvc5
from tests.unit.solver.test_render import fork


def test_a_read_from_the_end_of_many_lines_writes_a_program_of_bounded_size() -> None:
    # the input's own count is held to the cap, so a program over many lines stays small
    lines: Expression = ["splitlines", "s"]
    path = (
        fork([">=", ["len", lines], 1], taken=True),
        fork(["==", ["[]", lines, -1], "'z'"], taken=True),
    )
    origin = Origin(values={"s": "a\n" * 300})

    text = program(path, {"s": str}, origin).text

    assert len(text) < 2_000_000, len(text)


@needs_cvc5
@pytest.mark.parametrize(
    ("parts", "seed"),
    [(["split", "s", "','"], "a"), (["split", ["strip", "s"], "','"], "a")],
    ids=["the input's string", "a changed string"],
)
def test_a_path_past_the_bound_is_a_miss_that_says_so_never_unsat(
    parts: Expression, seed: str
) -> None:
    path = (
        fork(["==", ["len", parts], "n"], taken=True),
        fork(["==", "n", 40], taken=True),
    )
    args = Seed.of({"s": seed, "n": 0})

    answer = solve(path, args.leaves, 10.0, args.lists, args.values)

    # Python takes this path with 40 pieces, past the bound of 3: the held ask is unsat, and
    # the loosened one, which has an answer, says the fork is unknown
    assert isinstance(answer, Unknown), answer


@needs_cvc5
def test_a_path_that_needs_no_more_pieces_than_the_bound_is_answered_held() -> None:
    parts: Expression = ["split", "s", "','"]
    path = (
        fork(["<", ["len", parts], 20], taken=False),
        fork(["==", ["len", parts], "n"], taken=True),
    )
    args = Seed.of({"s": "a", "n": 0})

    answer = solve(path, args.leaves, 10.0, args.lists, args.values)

    # twenty pieces is below the bound of 22, so the held program answers
    assert isinstance(answer, Sat), answer
    values = dict(apply(args, answer.model).args)
    count = len(str(values["s"]).split(","))
    assert count >= 20 and values["n"] == count, values


@needs_cvc5
@pytest.mark.parametrize(
    "other",
    ["n", ["len", ["split", "t"]]],
    ids=["a tracked int", "another split's count"],
)
def test_a_whitespace_count_that_meets_a_term_is_answered_at_once(other: Expression) -> None:
    words: Expression = ["split", "s"]
    path = (fork(["==", ["len", words], other], taken=True), fork([">", "n", 2], taken=True))
    seed = Seed.of({"s": "a", "t": "b c", "n": 0})

    started = time.perf_counter()
    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    assert isinstance(answer, Sat), answer
    assert time.perf_counter() - started < 3.0
    args = dict(apply(seed, answer.model).args)
    s, t, n = str(args["s"]), str(args["t"]), args["n"]
    counted = n if other == "n" else len(t.split())
    assert len(s.split()) == counted and isinstance(n, int) and n > 2, args


@needs_cvc5
def test_an_unrelated_number_on_the_path_leaves_a_tie_small() -> None:
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
def test_the_last_of_a_few_lines_is_chosen_among_every_count_once_their_own_is_unsat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lines: Expression = ["splitlines", "s"]
    path = (
        fork([">=", ["len", lines], 1], taken=True),
        fork(["==", ["[]", lines, -1], "'end'"], taken=True),
        fork([">", ["len", lines], 7], taken=True),
    )
    seed = Seed.of({"s": "a\nb\nend"})
    asked: list[bool] = []
    ask = cvc5_module._ask

    def recorded(written: Program, timeout: float) -> Any:
        asked.append(written.fixed_few)
        return ask(written, timeout)

    monkeypatch.setattr(cvc5_module, "_ask", recorded)

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # read where the input's three lines put the last one, eight lines are unsat; the ask
    # after it chooses the last line among every count, where the path's eight lines can be
    assert asked[:2] == [True, False], asked
    assert not isinstance(answer, Unsat), answer
    if isinstance(answer, Sat):
        text = str(apply(seed, answer.model).args["s"])
        assert text.splitlines()[-1] == "end" and len(text.splitlines()) > 7, text


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
def test_a_count_cut_by_a_slice_is_bound_past_what_the_slice_leaves_out() -> None:
    parts: Expression = ["split", "s", "','"]
    path = (fork([">", ["len", ["[:]", parts, 2, None]], 3], taken=True),)
    seed = Seed.of({"s": "a"})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # six pieces, two of them before the slice: the bound counts the two
    assert isinstance(answer, Sat), answer
    text = str(apply(seed, answer.model).args["s"])
    assert len(text.split(",")[2:]) > 3, text


@needs_cvc5
def test_a_loosened_ask_holds_no_rsplit_past_its_walk_to_its_limit() -> None:
    parts: Expression = ["rsplit", "s", "','", LONGEST_WALK + 1]
    path = (
        fork([">", ["len", parts], 0], taken=True),
        fork(["==", ["[]", parts, 0], "'a,b'"], taken=True),
    )
    seed = Seed.of({"s": "a"})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # Python takes this path with 'a,b' and seventeen more pieces, a string the read's
    # restriction rules out: that is a miss that says so, never unsat
    assert isinstance(answer, Unknown), answer


@needs_cvc5
def test_a_count_held_below_its_forks_is_a_miss_without_asking() -> None:
    parts: Expression = ["split", "s", "','"]
    path = (
        fork(["<", ["len", parts], 36], taken=False),
        fork(["==", ["len", parts], "n"], taken=True),
    )
    seed = Seed.of({"s": "a" + ",a" * 39, "n": 0})

    answer = solve(path, seed.leaves, 3.0, seed.lists, seed.values)

    # the held program holds 34 pieces against a fork that needs 36, so neither it nor the
    # loosened one, which ran to the limit, is asked: the fork is a miss at once
    assert isinstance(answer, Unknown), answer


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


# a read from the end and the path's number compared with the count: whether the program puts
# the piece where the input's own few pieces put it, to be chosen among every count after
FIXED_FEW: dict[str, tuple[Expression, str, int, bool]] = {
    "the last of three lines, eight asked": (["splitlines", "s"], "a\nb\nend", 7, True),
    "the last of three lines, ten asked": (["splitlines", "s"], "a\nb\nend", 9, False),
    "the last of nine lines": (["splitlines", "s"], "a\n" * 8 + "end", 7, False),
    "a piece a reversed walk reads": (["split", "s", "','"], "a,end", 7, False),
}


@pytest.mark.parametrize(
    ("split", "text", "number", "fixed"), FIXED_FEW.values(), ids=list(FIXED_FEW)
)
def test_a_few_pieces_are_chosen_among_later_only_where_the_choice_answers(
    split: Expression, text: str, number: int, fixed: bool
) -> None:
    path = (
        fork([">=", ["len", split], 1], taken=True),
        fork(["==", ["[]", split, -1], "'end'"], taken=True),
        fork([">", ["len", split], number], taken=True),
    )

    written = program(path, {"s": str}, Origin(values={"s": text}))

    assert written.fixed_few is fixed


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


@needs_cvc5
def test_a_count_no_read_from_the_end_needs_past_its_bound_is_a_miss_at_once() -> None:
    parts: Expression = ["split", "s", "','"]
    path = (
        fork(["==", ["len", parts], "n"], taken=True),
        fork(["==", "n", 40], taken=True),
    )
    seed = Seed.of({"s": "a,b,c,d", "n": 4})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # tied by walks, the held ask is unsat past the bound of 6 and the loosened one says so
    assert isinstance(answer, Unknown), answer


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
