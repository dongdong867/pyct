"""cvc5 against Python on the forks a tracked range records: membership as one fork, with the
step's sign and a tracked bound, and the passes of a walk."""

import itertools

import pytest

from pyct.core.branch import Branch, Expression, Site
from pyct.solver.answer import Sat, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.render import program
from tests.unit.solver.agreement import needs_cvc5

SITE = Site(file="m.py", line=2, col=7)


def _fork(expression: Expression, *, taken: bool = True) -> Branch:
    return Branch(expression=expression, taken=taken, site=SITE)


def _model(path: tuple[Branch, ...], leaves: dict[str, type]) -> dict[str, int]:
    """The ints cvc5 answers the path with, by name."""
    answer = solve(path, leaves, 10.0)
    assert isinstance(answer, Sat), answer
    model = {name: value for name, value in answer.model.items() if type(value) is int}
    assert model.keys() == leaves.keys(), answer.model
    return model


# plain ranges of each shape: a start and a stop, a step above 1, a negative step, and empty
PLAIN: list[tuple[int, ...]] = [(1, 65536), (0, 10, 2), (10, 0, -3), (-4, 5, 3), (5, 5), (3, 9, -1)]


@needs_cvc5
@pytest.mark.parametrize(("bounds", "taken"), list(itertools.product(PLAIN, [True, False])))
def test_a_tracked_int_in_a_plain_range_agrees_with_python(
    bounds: tuple[int, ...], taken: bool
) -> None:
    # near the range, so an answer outside it is a small number cvc5 finds
    path = (
        _fork(["in", "x", ["range", *bounds]], taken=taken),
        _fork(["<=", -20, "x"]),
        _fork(["<", "x", 20]),
    )
    answer = solve(path, {"x": int}, 10.0)

    expected = [x for x in range(-20, 20) if (x in range(*bounds)) == taken]
    if not expected:
        assert isinstance(answer, Unsat), answer
        return
    assert isinstance(answer, Sat), answer
    assert answer.model["x"] in expected


@needs_cvc5
def test_not_in_a_range_is_the_other_side() -> None:
    model = _model((_fork(["not in", "x", ["range", 0, 10, 2]], taken=False),), {"x": int})

    assert model["x"] in range(0, 10, 2)


@needs_cvc5
def test_a_plain_int_in_a_range_with_tracked_bounds() -> None:
    model = _model((_fork(["in", 5, ["range", "a", "b"]]),), {"a": int, "b": int})

    assert 5 in range(model["a"], model["b"])


@needs_cvc5
def test_a_tracked_step_answers_by_its_sign() -> None:
    step = [_fork(["!=", "k", 0]), _fork([">", "k", 0], taken=False)]
    path = (*step, _fork(["in", "x", ["range", 10, 0, "k"]]), _fork(["==", ["%", "x", 4], 1]))

    model = _model(path, {"x": int, "k": int})

    assert model["x"] in range(10, 0, model["k"])


@needs_cvc5
def test_a_tracked_negative_step_over_an_upward_span_holds_nothing() -> None:
    step = [_fork(["!=", "k", 0]), _fork([">", "k", 0], taken=False)]
    path = (*step, _fork(["in", "x", ["range", 0, 10, "k"]]))

    assert isinstance(solve(path, {"x": int, "k": int}, 10.0), Unsat)


@needs_cvc5
def test_a_tracked_bool_bound_reads_as_the_int_it_is() -> None:
    path = (_fork(["in", 0, ["range", 0, [">", "x", 3]]]),)

    model = _model(path, {"x": int})

    assert isinstance(model["x"], int) and model["x"] > 3


@needs_cvc5
def test_a_walk_over_a_tracked_step_flips_its_exit() -> None:
    passes = [_fork([">", 10, "k"]), _fork([">", 10, ["*", 2, "k"]])]
    path = (_fork(["!=", "k", 0]), _fork([">", "k", 0]), *passes, _fork([">", 10, ["*", 3, "k"]]))

    model = _model(path, {"k": int})

    assert len(range(0, 10, model["k"])) >= 4


def test_a_range_is_written_as_its_bounds_inside_the_membership() -> None:
    text = program((_fork(["in", "x", ["range", 0, "n"]]),), {"x": int, "n": int}).text

    assert "(assert (and (<= 0 |arg.x|) (< |arg.x| |arg.n|)))" in text.splitlines()
