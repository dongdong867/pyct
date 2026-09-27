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


@needs_cvc5
@pytest.mark.parametrize("taken", [True, False])
def test_a_bool_item_in_a_range_reads_as_the_int_it_is(taken: bool) -> None:
    path = (_fork(["in", ["<", "x", 3], ["range", 1, 2]], taken=taken),)

    model = _model(path, {"x": int})

    assert ((model["x"] < 3) in range(1, 2)) is taken


@needs_cvc5
def test_a_plain_bool_item_in_a_tracked_range() -> None:
    model = _model((_fork(["in", True, ["range", 0, "n"]]),), {"n": int})

    assert True in range(model["n"])


# pairs of ranges with tracked bounds, each written as its arguments; `a`, `b`, `c` and `k` are
# ints the solver picks, kept small so a brute force over them finds every answer Python has
EQUALITIES: list[tuple[Expression, Expression]] = [
    (["range", 0, "a"], ["range", 0, "b"]),
    (["range", "a", "b"], ["range", 0, 3]),
    (["range", "a", 5], ["range", "b", 5, 2]),
    (["range", "a", "b", "k"], ["range", 0, 1]),
    (["range", "a", "b", "k"], ["range", 4, 0, -2]),
    (["range", 0, "a", "k"], ["range", 0, "b", 3]),
]
_SMALL = range(-4, 5)


def _python_equal(pair: tuple[Expression, Expression], values: dict[str, int]) -> bool | None:
    """Python's answer for the pair at these values, or None where a range would refuse a zero
    step."""
    built = []
    for form in pair:
        assert isinstance(form, list)
        bounds = [values[part] if isinstance(part, str) else part for part in form[1:]]
        if len(bounds) == 3 and bounds[2] == 0:
            return None
        built.append(range(*bounds))  # pyrefly: ignore[no-matching-overload]
    return built[0] == built[1]


@needs_cvc5
@pytest.mark.parametrize(("pair", "taken"), list(itertools.product(EQUALITIES, [True, False])))
def test_an_equality_of_two_ranges_agrees_with_python(
    pair: tuple[Expression, Expression], taken: bool
) -> None:
    names = sorted({part for form in pair for part in form[1:] if isinstance(part, str)})  # pyrefly: ignore
    bounded = [fork for name in names for fork in (_fork(["<=", -4, name]), _fork(["<", name, 5]))]
    stepped = [_fork(["!=", "k", 0])] if "k" in names else []
    path = (*bounded, *stepped, _fork(["==", *pair], taken=taken))
    answer = solve(path, dict.fromkeys(names, int), 10.0)

    found = [
        values
        for values in (
            dict(zip(names, combo, strict=True))
            for combo in itertools.product(_SMALL, repeat=len(names))
        )
        if _python_equal(pair, values) is taken
    ]
    if not found:
        assert isinstance(answer, Unsat), answer
        return
    assert isinstance(answer, Sat), answer
    assert _python_equal(pair, {name: answer.model[name] for name in names}) is taken  # pyrefly: ignore


@needs_cvc5
def test_an_inequality_of_two_ranges_is_the_other_side() -> None:
    model = _model((_fork(["!=", ["range", 0, "a"], ["range", 0, 3]], taken=False),), {"a": int})

    assert range(model["a"]) == range(3)
