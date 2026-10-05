"""A split's piece a tracked operand handed out, ``["[]", split, ["pin", k, operand, value]]``:
piece k, read only while the operand has its value. A fork before the one aimed at holds only
there, and the fork aimed at reads the piece where the run read it."""

import pytest

from pyct.binding.bind import Seed
from pyct.binding.model import apply
from pyct.core.branch import Expression
from pyct.solver.answer import Sat
from pyct.solver.cvc5 import solve
from pyct.solver.lists import Origin
from pyct.solver.render import program
from pyct.solver.split_lists import UnknownCountError
from tests.unit.solver.agreement import needs_cvc5
from tests.unit.solver.test_render import fork

SPLIT: Expression = ["split", "s", "','"]
LEAVES = {"s": str, "n": int}
ORIGIN = Origin(values={"s": "a,b", "n": 1})


def _piece(*pins: tuple[Expression, int]) -> Expression:
    at: Expression = 1
    for operand, value in pins:
        at = ["pin", at, operand, value]
    return ["[]", SPLIT, at]


def test_a_fork_before_the_aimed_one_holds_only_while_the_index_has_its_value() -> None:
    path = (
        fork(["==", _piece(("n", 1)), "'z'"], taken=False),
        fork(["==", ["len", SPLIT], 1], taken=True),
    )

    text = program(path, LEAVES, ORIGIN).text

    # the piece is there, and is the one the fork reads, only while n is 1
    assert "(assert (=> (= |arg.n| 1) " in text, text
    assert "(ite (= |arg.n| 1) " in text, text
    assert "(assert (= |arg.n| 1))" not in text, text


def test_the_aimed_fork_reads_the_piece_where_the_run_read_it() -> None:
    path = (fork(["==", _piece(("n", 1)), "'z'"], taken=True),)

    text = program(path, LEAVES, ORIGIN).text

    assert "(assert (= |arg.n| 1))" in text, text


def test_a_piece_pinned_twice_is_read_while_both_operands_have_their_values() -> None:
    path = (fork(["==", _piece(("n", 1), ("m", 0)), "'z'"], taken=True),)

    text = program(path, {**LEAVES, "m": int}, ORIGIN).text

    assert "(assert (and (= |arg.n| 1) (= |arg.m| 0)))" in text, text


@needs_cvc5
def test_cvc5_flips_the_count_past_a_piece_read_at_a_tracked_index() -> None:
    path = (
        fork([">=", "n", 0], taken=True),
        fork(["<", "n", ["len", SPLIT]], taken=True),
        fork(["==", _piece(("n", 1)), "'z'"], taken=False),
        fork(["==", ["len", SPLIT], 1], taken=True),
    )
    seed = Seed.of({"s": "a,b", "n": 1})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # one piece holds no piece 1: the index moves with the count, as plain Python's would
    assert isinstance(answer, Sat), answer
    args = dict(apply(seed, answer.model).args)
    s, n = args["s"], args["n"]
    assert isinstance(s, str) and isinstance(n, int)
    assert len(s.split(",")) == 1 and 0 <= n < 1, args


@needs_cvc5
def test_cvc5_flips_a_piece_read_at_a_tracked_index_where_the_run_read_it() -> None:
    path = (
        fork([">=", "n", 0], taken=True),
        fork(["<", "n", ["len", SPLIT]], taken=True),
        fork(["==", _piece(("n", 1)), "'z'"], taken=True),
    )
    seed = Seed.of({"s": "a,b", "n": 1})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    assert isinstance(answer, Sat), answer
    args = dict(apply(seed, answer.model).args)
    s, n = args["s"], args["n"]
    assert isinstance(s, str) and n == 1 and s.split(",")[1] == "z", args


def test_a_pin_on_an_operand_that_reads_the_count_holds_the_string_to_c_star_pieces() -> None:
    operand: Expression = ["-", ["len", SPLIT], "n"]
    path = (fork(["==", ["[]", SPLIT, ["pin", 1, operand, 1]], "'z'"], taken=True),)

    text = program(path, LEAVES, ORIGIN).text

    # `len(parts) - n` is 1 only while the string has the two pieces it had
    held = next(line for line in text.splitlines() if line.startswith("(assert (and (and (= "))
    assert held.count("str.indexof") >= 2, text


@needs_cvc5
def test_cvc5_reads_a_piece_from_the_end_where_python_reads_it() -> None:
    path = (
        fork([">", "n", 0], taken=True),
        fork(["<=", "n", ["len", SPLIT]], taken=True),
        fork(["==", ["[]", SPLIT, ["pin", -1, ["-", "n"], -1]], "'z'"], taken=True),
    )
    seed = Seed.of({"s": ",".join("a" * 9), "n": 1})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    assert isinstance(answer, Sat), answer
    args = dict(apply(seed, answer.model).args)
    s, n = args["s"], args["n"]
    assert isinstance(s, str) and n == 1 and s.split(",")[-1] == "z", args


def test_a_pin_on_the_count_of_a_string_with_no_input_value_is_a_miss() -> None:
    operand: Expression = ["-", ["len", SPLIT], "n"]
    path = (fork(["==", ["[]", SPLIT, ["pin", 1, operand, 1]], "'z'"], taken=True),)

    # no c* holds the count, and a line reads it: never a guess
    with pytest.raises(UnknownCountError):
        program(path, LEAVES, Origin(values={"n": 1}))


def test_the_aimed_fork_holds_each_pin_it_reads() -> None:
    first: Expression = ["[]", SPLIT, ["pin", 0, "n", 0]]
    second: Expression = ["[]", SPLIT, ["pin", 1, "m", 1]]
    path = (fork(["==", first, second], taken=True),)

    text = program(path, {**LEAVES, "m": int}, Origin(values={"s": "a,b", "n": 0, "m": 1})).text

    assert "(assert (= |arg.n| 0))" in text and "(assert (= |arg.m| 1))" in text, text


@needs_cvc5
def test_cvc5_keeps_the_count_a_read_through_a_cut_hangs_on() -> None:
    cut: Expression = ["[:]", SPLIT, 1, None]
    at: Expression = ["pin", ["pin", 8, ["-", "n"], -1], ["len", SPLIT], None]
    path = (
        fork([">", "n", 0], taken=True),
        fork(["<=", "n", ["len", cut]], taken=True),
        fork(["==", ["[]", SPLIT, at], "'z'"], taken=True),
    )
    seed = Seed.of({"s": ",".join("a" * 9), "n": 1})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # `p[1:][-n]` is piece 8 only while the string has its nine pieces
    assert isinstance(answer, Sat), answer
    args = dict(apply(seed, answer.model).args)
    s, n = args["s"], args["n"]
    assert isinstance(s, str) and n == 1 and s.split(",")[1:][-1] == "z", args
    assert len(s.split(",")) == 9, args
