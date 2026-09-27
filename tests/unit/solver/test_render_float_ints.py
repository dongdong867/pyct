"""An int meeting a double in SMT-LIB, the roundings to an Int, and a bound a form holds."""

from pathlib import Path

import pytest

from pyct.core.branch import Expression
from pyct.solver.answer import Sat, Unknown, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.floats import QUOTIENT_BOUND, finite, from_int, literal
from pyct.solver.render import program
from tests.unit.solver.test_cvc5 import fork
from tests.unit.solver.test_cvc5_floats import asked, fake_cvc5, needs_cvc5

LEAVES: dict[str, type] = {"n": int, "m": int, "x": float, "y": float}
N, M, X = "|arg.n|", "|arg.m|", "|arg.x|"


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


def test_a_bound_asked_for_its_core_is_named_through_a_literal() -> None:
    lines = _text(["==", ["//", "x", 2.5], 3.0], cores=True).splitlines()

    assert lines[0] == "(set-option :dump-unsat-cores true)"
    assert "(declare-const b!0 Bool)" in lines
    assert "(assert (! b!0 :named bound!0))" in lines
    assert any(line.startswith("(assert (=> b!0 ") for line in lines)


@pytest.mark.parametrize(
    "expression",
    [["==", ["%", "x", 2.5], 1.0], ["==", ["//", "n", 2], 1], ["==", ["floor", "x"], 1]],
    ids=["float modulo", "int floor division", "rounding"],
)
def test_a_form_exact_everywhere_holds_no_bound(expression: Expression) -> None:
    written = program((fork(expression, taken=True),), LEAVES, cores=True)

    assert not written.bounded
    assert "bound!" not in written.text


def test_an_unsat_whose_core_names_a_bound_is_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, "unsat\n", "unsat\n(\nbound!0\n)\n")
    monkeypatch.setenv("PATH", str(tmp_path))

    answer = solve((fork(["==", ["//", "n", 2.5], 3.0], taken=True),), {"n": int}, 10.0)

    # no float leaf is held finite, and the core is still asked for, since the program is bounded
    assert answer == Unknown()
    first, cored = asked(tmp_path)
    assert "dump-unsat-cores" not in "\n".join(first)
    assert cored[0] == "(set-option :dump-unsat-cores true)"


def test_an_unsat_whose_core_names_no_bound_is_the_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, "unsat\n", "unsat\n(\n)\n")
    monkeypatch.setenv("PATH", str(tmp_path))

    answer = solve((fork(["==", ["//", "n", 2.5], 3.0], taken=True),), {"n": int}, 10.0)

    assert answer == Unsat()
    assert len(asked(tmp_path)) == 2


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
