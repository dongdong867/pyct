"""An int meeting a double in SMT-LIB, the roundings to an Int, and a bound a form holds."""

import math
import subprocess
from pathlib import Path

import pytest

from pyct.core.branch import Expression
from pyct.solver.answer import Sat, Unknown, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.floats import QUOTIENT_BOUND, finite, floor_division, from_int, literal
from pyct.solver.render import program
from tests.unit.solver.test_cvc5 import NOT_UNKNOWN, fork
from tests.unit.solver.test_cvc5_floats import asked, fake_cvc5, needs_cvc5

LEAVES: dict[str, type] = {"n": int, "m": int, "x": float, "y": float}
N, M, X = "|arg.n|", "|arg.m|", "|arg.x|"


def run_cvc5(lines: list[str]) -> str:
    """cvc5's first word on a program."""
    answer = subprocess.run(
        ["cvc5", "--lang", "smt", "--quiet"],
        input="\n".join(lines) + "\n",
        capture_output=True,
        text=True,
        check=False,
    )
    return answer.stdout.split()[0]


def _text(expression: Expression, *, cores: bool = False) -> str:
    return program((fork(expression, taken=True),), LEAVES, cores=cores).text


def test_an_int_meeting_a_double_is_converted_as_python_converts_it() -> None:
    text = _text([">", ["+", "n", 0.5], "x"])

    assert f"(fp.gt (fp.add RNE {from_int(N)} {literal(0.5)}) {X})" in text
    # an int stays an Int in the answer, so it is declared one
    assert f"(declare-const {N} Int)" in text


def test_true_division_between_ints_divides_as_doubles() -> None:
    text = _text([">=", ["/", "n", "m"], 2.5])

    assert f"(fp.geq (fp.div RNE {from_int(N)} {from_int(M)}) {literal(2.5)})" in text


def test_an_int_compared_with_a_float_literal_is_compared_as_a_double() -> None:
    text = _text(["<", "n", 2.5])

    assert f"(fp.lt {from_int(N)} {literal(2.5)})" in text


def test_a_rounding_answers_an_int_that_meets_an_int() -> None:
    text = _text(["<", ["floor", "x"], "n"])

    assert f"(< (to_int (fp.to_real (fp.roundToIntegral RTN {X}))) {N})" in text


@pytest.mark.parametrize(
    ("head", "mode"), [("floor", "RTN"), ("ceil", "RTP"), ("trunc", "RTZ"), ("round", "RNE")]
)
def test_each_rounding_rounds_in_its_own_direction(head: str, mode: str) -> None:
    text = _text(["==", [head, "x"], 3])

    assert f"(= (to_int (fp.to_real (fp.roundToIntegral {mode} {X}))) 3)" in text


def test_the_finite_fork_is_a_double_neither_nan_nor_infinite() -> None:
    assert f"(assert {finite(X)})" in _text(["isfinite", "x"])


def test_a_float_floor_division_holds_its_bound_on_the_path() -> None:
    written = program((fork(["==", ["//", "x", 2.5], 3.0], taken=True),), LEAVES)

    assert written.bounded
    assert f"(< q! {QUOTIENT_BOUND})" in written.text


def test_a_bound_left_out_writes_the_term_past_it_as_a_double_of_its_own() -> None:
    fork_ = fork(["==", ["//", "x", 2.5], 3.0], taken=True)
    held = program((fork_,), LEAVES).text
    left_out = program((fork_,), LEAVES, bounded=False).text

    # holding the bound, the term is the floor everywhere, which cvc5 answers far faster; left
    # out, the term past it is a double declared for it alone
    assert "(declare-const e!" not in held
    assert "(declare-const e!0 Float64)" in left_out
    bound = [line for line in held.splitlines() if line.startswith("(assert (or (or (fp.isNaN")]
    assert len(bound) == 1
    assert bound[0] not in left_out


@pytest.mark.parametrize(
    "expression",
    [["==", ["%", "x", 2.5], 1.0], ["==", ["//", "n", 2], 1], ["==", ["floor", "x"], 1]],
    ids=["float modulo", "int floor division", "rounding"],
)
def test_a_form_exact_everywhere_holds_no_bound(expression: Expression) -> None:
    written = program((fork(expression, taken=True),), LEAVES, cores=True)

    assert not written.bounded
    assert "(< q! " not in written.text


@pytest.mark.parametrize(
    ("unbounded", "answer"),
    [("unsat\n", Unsat()), (f"sat\n((arg.n 9))\n{NOT_UNKNOWN}", Unknown())],
    ids=["unsat", "sat"],
)
def test_a_bounded_unsat_is_asked_again_without_its_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, unbounded: str, answer: object
) -> None:
    fake_cvc5(tmp_path, "unsat\n", unbounded)
    monkeypatch.setenv("PATH", str(tmp_path))

    solved = solve((fork(["==", ["//", "n", 2.5], 3.0], taken=True),), {"n": int}, 10.0)

    # without the bound an unsat covers every value Python gives, and a model past the bound
    # may not be Python's; no float leaf is held finite, so no core is asked for
    assert solved == answer
    first, unbounded_ask = asked(tmp_path)
    assert "(declare-const e!0 Float64)" in unbounded_ask
    assert "(declare-const e!0 Float64)" not in first


def test_an_unbounded_program_is_asked_nothing_more_after_an_unsat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, "unsat\n")
    monkeypatch.setenv("PATH", str(tmp_path))

    solved = solve((fork(["==", ["%", "n", 2.5], 3.0], taken=True),), {"n": int}, 10.0)

    assert solved == Unsat()
    assert len(asked(tmp_path)) == 1


@needs_cvc5
def test_cvc5_answers_unknown_where_only_a_quotient_past_the_bound_takes_the_path() -> None:
    # 1e300 // 1.0 is 1e300 in Python, but that quotient is past what the form is exact inside
    past = solve((fork(["==", ["//", "x", 1.0], 1e300], taken=True),), {"x": float}, 10.0)
    # no double has a whole-number floor of 3.5, inside the bound or past it
    never = solve((fork(["==", ["//", "x", 2.5], 3.5], taken=True),), {"x": float}, 10.0)
    inside = solve((fork(["==", ["//", "x", 2.5], 3.0], taken=True),), {"x": float}, 10.0)

    assert (past, never) == (Unknown(), Unsat())
    assert isinstance(inside, Sat)
    value = inside.model["x"]
    assert isinstance(value, float) and value // 2.5 == 3.0


@pytest.mark.parametrize(
    ("expression", "bool_term"),
    [
        ([">", ["/", "n", True], 2.5], from_int("1")),
        ([">", ["/", False, "n"], 2.5], from_int("0")),
        ([">", ["/", "n", [">", "m", 3]], 2.5], from_int(f"(ite (> {M} 3) 1 0)")),
    ],
    ids=["plain true", "plain false", "tracked"],
)
def test_a_bool_under_true_division_divides_as_the_int_it_is(
    expression: Expression, bool_term: str
) -> None:
    text = _text(expression)

    assert bool_term in text
    assert "(fp.div RNE " in text


@needs_cvc5
def test_past_its_bound_the_floor_division_term_can_be_what_python_gives() -> None:
    # CPython's two roundings move this quotient, past the bound, off the true floor
    x, y = 9395975219820272.0, 1.1
    term, _ = floor_division(literal(x), literal(y), "past")
    lines = [
        "(set-logic ALL)",
        "(declare-const past Float64)",
        f"(assert (fp.eq {term} {literal(x // y)}))",
        "(check-sat)",
    ]

    assert run_cvc5(lines) == "sat"


def test_a_bounded_path_frees_a_held_leaf_its_core_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    infinity = f"(fp #b0 #b{'1' * 11} #b{'0' * 52})"
    sat = f"sat\n((arg.x {infinity}))\n{NOT_UNKNOWN}"
    fake_cvc5(tmp_path, "unsat\n", "unsat\n(\nfinite!arg.x\n)\n", sat)
    monkeypatch.setenv("PATH", str(tmp_path))
    prefix = (fork(["!=", ["//", "x", 1.0], 0.0], taken=True),)

    answer = solve(prefix, {"x": float}, 10.0)

    assert answer == Sat({"x": math.inf})
    assert len(asked(tmp_path)) == 3


@needs_cvc5
def test_cvc5_frees_a_leaf_past_the_bound_where_an_infinity_takes_the_path() -> None:
    prefix = (
        fork(["!=", ["//", "x", 1.0], 0.0], taken=True),
        fork([">", "x", 1e20], taken=True),
    )

    answer = solve(prefix, {"x": float}, 10.0)

    # every finite x above 1e20 has a quotient past the bound; inf // 1.0 is NaN, unequal to 0.0
    assert answer == Sat({"x": math.inf})
