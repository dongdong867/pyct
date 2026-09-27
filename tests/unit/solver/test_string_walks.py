"""cvc5 against Python on the paths a walk over a string records: one fork a pass, and the
character each pass reads, at every position of a long string."""

import pytest

from pyct.core.branch import Branch, Expression, Site
from pyct.solver.answer import Sat, Unsat
from pyct.solver.cvc5 import solve
from tests.unit.solver.agreement import disagrees, flipped_path, needs_cvc5
from tests.unit.solver.test_string_pieces import PYTHON_HEADS

SITE = Site(file="m.py", line=2, col=13)


def _walk(passes: int) -> list[tuple[Expression, Expression | None]]:
    """`for c in s: if c == "x":` over ``passes`` passes: each pass's fork, then its compare."""
    return [(["==", ["[]", "s", at], "'x'"], [">", ["len", "s"], at]) for at in range(passes)]


# the fork each case flips on a walk over forty letters, none of them x: the walk's exit asks
# for a longer string, and the last pass's compare for an x at the fortieth letter
FLIPS: dict[str, int] = {"the exit": 41, "the last compare": 40}


@needs_cvc5
@pytest.mark.parametrize("passes", FLIPS.values(), ids=list(FLIPS))
def test_cvc5_answers_a_walk_over_forty_letters_inside_its_limit(passes: int) -> None:
    path = flipped_path("ab" * 20, _walk(passes), PYTHON_HEADS)

    answer = solve(path, {"s": str}, 10.0)

    assert isinstance(answer, Sat), answer
    assert not disagrees(path, answer, PYTHON_HEADS, [], 0)


@needs_cvc5
def test_cvc5_answers_a_walk_over_four_hundred_letters_inside_its_limit() -> None:
    path = flipped_path("ab" * 200, _walk(401), PYTHON_HEADS)

    answer = solve(path, {"s": str}, 10.0)

    assert isinstance(answer, Sat), answer
    assert not disagrees(path, answer, PYTHON_HEADS, [], 0)


def _fork(expression: Expression, *, taken: bool) -> Branch:
    return Branch(expression=expression, taken=taken, site=SITE)


@needs_cvc5
def test_a_character_past_the_end_is_the_empty_string_where_the_path_allows_it() -> None:
    # nothing on the path says s is four long, so its fourth character may be past the end,
    # which the solver reads as the empty string, as it reads `str.at` there
    path = (_fork(["==", ["[]", "s", 3], "''"], taken=True),)

    answer = solve(path, {"s": str}, 10.0)

    assert isinstance(answer, Sat), answer
    s = answer.model["s"]
    assert isinstance(s, str) and len(s) <= 3


@needs_cvc5
def test_a_character_the_path_holds_there_is_never_the_empty_string() -> None:
    path = (
        _fork([">", ["len", "s"], 3], taken=True),
        _fork(["==", ["[]", "s", 3], "''"], taken=True),
    )

    assert isinstance(solve(path, {"s": str}, 10.0), Unsat)


@needs_cvc5
def test_cvc5_answers_two_reads_far_apart_inside_a_second() -> None:
    # `s[0]` and `s[20000]`: the path reads two letters, so the program writes no more than
    # the reads it has, however far apart they sit
    far = 20_000
    path = (
        _fork([">", ["len", "s"], far], taken=True),
        _fork(["==", ["[]", "s", 0], "'a'"], taken=True),
        _fork(["==", ["[]", "s", far], "'b'"], taken=True),
    )

    answer = solve(path, {"s": str}, 1.0)

    assert isinstance(answer, Sat), answer
    s = answer.model["s"]
    assert isinstance(s, str) and s[0] == "a" and s[far] == "b"
