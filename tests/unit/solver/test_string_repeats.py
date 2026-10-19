"""A str repeated a plain number of times in SMT-LIB: the term strings.py writes, and cvc5 held
against Python on it."""

import random
from collections.abc import Callable

import pytest

from pyct.core.branch import Branch, Expression
from pyct.solver.answer import Sat, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.strings import repeated
from tests.unit.solver.agreement import SITE, needs_cvc5
from tests.unit.solver.test_render import render


def _fork(expression: Expression, *, taken: bool = True) -> Branch:
    return Branch(expression=expression, taken=taken, site=SITE)


def test_a_repeat_is_its_copies_joined_with_the_count_on_either_side() -> None:
    assert repeated("s", "3") == "(str.++ s s s)"
    assert repeated("3", "s") == "(str.++ s s s)"
    assert repeated('"ab"', "2") == '(str.++ "ab" "ab")'


def test_one_copy_is_the_string_itself() -> None:
    assert repeated("(str.at s 0)", "1") == "(str.at s 0)"


@pytest.mark.parametrize("expression", [["*", "s", 2], ["*", 2, "s"]])
def test_render_writes_a_repeat_on_either_side_as_a_string(expression: Expression) -> None:
    text = render((_fork(["==", expression, "'abab'"]),), {"s": str})

    assert '(= (str.++ |arg.s| |arg.s|) "abab")' in text


# a repeat inside each kind of fork the target may write on it, and what Python makes of it
_CHECKS: list[tuple[Callable[[str, int], Expression], Callable[[str, int], bool]]] = [
    (lambda s, k: ["==", ["*", "s", k], repr("ab" * k)], lambda s, k: s * k == "ab" * k),
    (lambda s, k: ["==", ["len", ["*", k, "s"]], 3 * k], lambda s, k: len(k * s) == 3 * k),
    (lambda s, k: ["startswith", ["*", "s", k], "'aba'"], lambda s, k: (s * k).startswith("aba")),
    (lambda s, k: ["in", "'ba'", ["*", "s", k]], lambda s, k: "ba" in s * k),
]


@needs_cvc5
@pytest.mark.parametrize("check", range(len(_CHECKS)))
@pytest.mark.parametrize("count", [1, 2, 5])
@pytest.mark.parametrize("taken", [True, False])
def test_cvc5_agrees_with_python_on_a_repeat(check: int, count: int, taken: bool) -> None:
    written, meant = _CHECKS[check]
    # short strings, so an answer is a value Python checks at once
    path = (_fork(written("s", count), taken=taken), _fork(["<=", ["len", "s"], 4]))

    answer = solve(path, {"s": str}, 10.0)

    if isinstance(answer, Unsat):
        letters = ["", "a", "b", "ab", "ba", "aba", "abab", "bab", "aab"]
        assert all(meant(s, count) != taken for s in letters)
        return
    assert isinstance(answer, Sat), answer
    s = answer.model["s"]
    assert isinstance(s, str)
    assert meant(s, count) == taken


@needs_cvc5
def test_cvc5_agrees_with_python_on_random_repeats() -> None:
    rng = random.Random(0)
    for _ in range(20):
        value = "".join(rng.choices("ab", k=rng.randint(0, 3)))
        count = rng.randint(1, 6)
        path = (_fork(["==", ["*", "s", count], repr(value * count)]),)

        answer = solve(path, {"s": str}, 10.0)

        assert isinstance(answer, Sat), answer
        s = answer.model["s"]
        assert isinstance(s, str) and s * count == value * count
