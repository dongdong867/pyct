"""A split's count bound by what the path needs: the numbers its forks compare the count with,
directly or through a tracked int it meets, and the input's own count only where a read from
the end puts a piece at a count; with cvc5 held against Python on each."""

import pytest

from pyct.binding.bind import Seed
from pyct.binding.model import apply
from pyct.core.branch import Expression
from pyct.solver.answer import Sat
from pyct.solver.cvc5 import solve
from tests.unit.solver.agreement import needs_cvc5
from tests.unit.solver.test_render import fork

LINES: Expression = ["splitlines", "s"]
REST: Expression = ["[:]", LINES, 2, None]


def _many(count: int) -> str:
    return "a\n" * (count - 1) + "x"


@needs_cvc5
@pytest.mark.parametrize("count", [8, 12, 16])
def test_the_last_of_many_lines_past_a_tracked_count_is_flipped(count: int) -> None:
    path = (
        fork([">", ["len", LINES], "n"], taken=True),
        fork([">=", ["len", LINES], 1], taken=True),
        fork(["==", ["[]", LINES, -1], "'end'"], taken=True),
    )
    seed = Seed.of({"s": _many(count), "n": 0})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # the last line is read by one look, at no count, so the count is tied only as far as the
    # path's own numbers need, where a tie to every line ran past the limit or kept the string
    assert isinstance(answer, Sat), answer
    args = apply(seed, answer.model).args
    lines, n = str(args["s"]).splitlines(), args["n"]
    assert isinstance(n, int) and lines[-1] == "end" and len(lines) > n, args


@needs_cvc5
@pytest.mark.parametrize("count", [8, 12, 16])
def test_the_last_of_the_rest_of_many_lines_is_flipped(count: int) -> None:
    path = (
        fork(["!=", ["len", REST], 0], taken=True),
        fork([">=", ["len", REST], 1], taken=True),
        fork(["==", ["[]", REST, -1], "'end'"], taken=True),
    )
    seed = Seed.of({"s": _many(count)})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    assert isinstance(answer, Sat), answer
    lines = str(apply(seed, answer.model).args["s"]).splitlines()
    assert lines[2:] and lines[2:][-1] == "end", lines


@needs_cvc5
@pytest.mark.parametrize("count", [3, 8, 12])
def test_a_count_a_tracked_int_meets_reaches_the_number_that_int_is_compared_with(
    count: int,
) -> None:
    path = (
        fork(["==", ["len", LINES], "n"], taken=True),
        fork(["==", "n", 8], taken=True),
    )
    seed = Seed.of({"s": _many(count), "n": count})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    # bound by the path's own numbers alone, the count could not reach eight
    assert isinstance(answer, Sat), answer
    args = apply(seed, answer.model).args
    assert len(str(args["s"]).splitlines()) == args["n"] == 8, args


@needs_cvc5
@pytest.mark.parametrize("count", [3, 9])
@pytest.mark.parametrize("settled", [False, True], ids=["a clamp", "a settled start"])
def test_a_piece_read_through_a_slice_keeps_the_condition_that_it_is_there(
    count: int, settled: bool
) -> None:
    # the last of the rest, read where the input's count puts it: through the slice, the
    # condition that the string has that many lines was dropped, and an answer of three lines
    # held 'end' at a ninth that Python never reads
    path = (
        *([fork([">=", ["len", LINES], 3], taken=True)] if settled else []),
        fork([">=", ["len", REST], 1], taken=True),
        fork(["==", ["[]", REST, -1], "'end'"], taken=True),
    )
    seed = Seed.of({"s": _many(count)})

    answer = solve(path, seed.leaves, 10.0, seed.lists, seed.values)

    assert isinstance(answer, Sat), answer
    lines = str(apply(seed, answer.model).args["s"]).splitlines()
    assert lines[2:] and lines[2:][-1] == "end", lines
