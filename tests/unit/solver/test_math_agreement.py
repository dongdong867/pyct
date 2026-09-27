"""cvc5 held against Python on the `math` functions pyct follows, and on paths through them."""

import itertools
import math
import struct
from collections.abc import Callable

import pytest

from pyct.core.branch import Expression
from pyct.solver.answer import Sat, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.floats import literal
from pyct.solver.heads import FORMS, OPERATORS
from tests.unit.solver.agreement import asked, needs_cvc5
from tests.unit.solver.test_cvc5 import fork
from tests.unit.solver.test_float_agreement import SPECIAL

# more doubles at the edges these functions have: a subnormal beside the smallest, a square
# that rounds, and a number just past a tolerance of the default one
EDGES = [*SPECIAL, 1e-320, 2.0, 0.1000000001, 0.10000000001, 1e-10]

# isclose's tolerances as a call may give them: the default, a wide one, an absolute one, none
TOLERANCES = [(1e-09, 0.0), (0.5, 0.0), (0.0, 1.0), (0.0, 0.0), (1e-09, 1e-300)]

type Case = tuple[str, tuple[float, ...], object]


def _cases() -> list[Case]:
    """Each followed function on each edge double, each pair, and each pair and tolerance.

    `sqrt` below zero raises in Python before it answers, so it has no answer to hold cvc5 to.
    """
    one: list[Case] = [
        (name, (value,), function(value))
        for name, function in (
            ("sqrt", math.sqrt),
            ("fabs", math.fabs),
            ("isnan", math.isnan),
            ("isinf", math.isinf),
            ("isfinite", math.isfinite),
        )
        for value in EDGES
        if name != "sqrt" or not value < 0.0
    ]
    pairs = list(itertools.product(EDGES, repeat=2))
    two: list[Case] = [("copysign", pair, math.copysign(*pair)) for pair in pairs]
    close: list[Case] = [
        ("isclose", (a, b, rel_tol, abs_tol), _close(a, b, rel_tol, abs_tol))
        for a, b in pairs
        for rel_tol, abs_tol in TOLERANCES
    ]
    return one + two + close


def _close(a: float, b: float, rel_tol: float, abs_tol: float) -> bool:
    return math.isclose(a, b, rel_tol=rel_tol, abs_tol=abs_tol)


def _term(head: str, operands: list[str]) -> str:
    """A head on rendered doubles, as render writes it: by its form, or by its operator."""
    form: Callable[..., str] | None = FORMS.get((head, float))
    if form is not None:
        return form(*operands)
    return f"({OPERATORS[(head, float)]} {' '.join(operands)})"


def _same(said: object, meant: object) -> bool:
    """The same truth value, or the same double to the bit; SMT-LIB has one NaN."""
    if isinstance(said, float) and isinstance(meant, float):
        both_nan = math.isnan(said) and math.isnan(meant)
        return both_nan or struct.pack(">d", said) == struct.pack(">d", meant)
    return said == meant


@needs_cvc5
def test_cvc5_agrees_with_python_to_the_bit_on_each_math_function_on_edge_doubles() -> None:
    cases = _cases()
    lines = ["(set-logic ALL)"]
    for at, (head, operands, meant) in enumerate(cases):
        sort = "Bool" if isinstance(meant, bool) else "Float64"
        term = _term(head, [literal(value) for value in operands])
        lines += [f"(declare-const v{at} {sort})", f"(assert (= v{at} {term}))"]
    lines += ["(check-sat)", f"(get-value ({' '.join(f'v{at}' for at in range(len(cases)))}))"]

    answers = asked(lines)

    assert len(answers) == len(cases)
    disagreements = [
        (head, operands, said)
        for (head, operands, meant), said in zip(cases, answers, strict=True)
        if not _same(said, meant)
    ]
    assert disagreements == []


# paths through each function, the last fork the one to take, and what Python says of an answer
PATHS: dict[str, tuple[list[tuple[Expression, bool]], Callable[[float], bool]]] = {
    "sqrt-above": (
        [(["not", ["<", "x", 0.0]], True), ([">", ["sqrt", "x"], 2.0], True)],
        lambda x: not x < 0.0 and math.sqrt(x) > 2.0,
    ),
    "sqrt-raises": ([(["not", ["<", "x", 0.0]], False)], lambda x: x < 0.0),
    "fabs": (
        [(["<", ["fabs", "x"], 1.0], True), (["<", "x", 0.0], True)],
        lambda x: -1.0 < x < 0.0,
    ),
    "copysign": (
        [(["<", ["copysign", 1.0, "x"], 0.0], True), (["==", "x", 0.0], True)],
        lambda x: x == 0.0 and math.copysign(1.0, x) < 0.0,
    ),
    "isnan": ([(["isnan", "x"], True)], math.isnan),
    "isinf": ([(["isinf", "x"], True), (["<", "x", 0.0], True)], lambda x: x == -math.inf),
    "isfinite": ([(["isfinite", "x"], False), (["isnan", "x"], False)], math.isinf),
    "isclose": (
        [(["isclose", "x", 0.1, 1e-09, 0.0], True), (["!=", "x", 0.1], True)],
        lambda x: math.isclose(x, 0.1) and x != 0.1,
    ),
    "not-isclose": (
        [(["isclose", "x", 0.1, 0.5, 0.0], False), (["<", "x", 0.2], True)],
        lambda x: not math.isclose(x, 0.1, rel_tol=0.5) and x < 0.2,
    ),
}


@needs_cvc5
@pytest.mark.parametrize("name", PATHS)
def test_cvc5_answers_a_path_through_a_math_function_as_python_takes_it(name: str) -> None:
    forks, python = PATHS[name]
    path = tuple(fork(expression, taken=taken) for expression, taken in forks)

    answer = solve(path, {"x": float}, 5.0)

    assert isinstance(answer, Sat), answer
    x = answer.model["x"]
    assert isinstance(x, float)
    assert python(x), x


@needs_cvc5
def test_cvc5_reads_a_tracked_int_as_the_double_python_converts_it_to() -> None:
    path = (fork(["not", ["<", "n", 0.0]], taken=True), fork([">", ["sqrt", "n"], 3.0], taken=True))

    answer = solve(path, {"n": int}, 5.0)

    assert isinstance(answer, Sat), answer
    n = answer.model["n"]
    assert isinstance(n, int) and math.sqrt(n) > 3.0


@needs_cvc5
def test_cvc5_finds_no_double_whose_square_root_is_negative() -> None:
    path = (
        fork(["not", ["<", "x", 0.0]], taken=True),
        fork(["<", ["sqrt", "x"], -0.0], taken=True),
    )

    assert isinstance(solve(path, {"x": float}, 5.0), Unsat)
