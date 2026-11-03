"""A result that wrote a tracked value in as its text holds that value as it was in each ask whose
path reads the result: a named hold, never freed, and an unsat that rests on it is unknown rather
than the path's (plan nested-floats-bools, 5.9)."""

import shutil
from pathlib import Path

import pytest

from pyct.core.branch import WAS, WROTE, Expression
from pyct.solver.answer import Sat, Unknown, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.written_in import STAYS_NAME
from tests.unit.solver.test_cvc5 import NOT_UNKNOWN, fork
from tests.unit.solver.test_cvc5_floats import asked, fake_cvc5

needs_cvc5 = pytest.mark.skipif(shutil.which("cvc5") is None, reason="cvc5 is not installed")


def hex_of(x: Expression, value: Expression) -> Expression:
    """`"%x|%d" % (x, y)`: x written in as the text it had, y an operand."""
    return [WROTE, ["%", "'1|%d'", "y"], [WAS, x, value]]


@needs_cvc5
def test_an_unsat_that_rests_on_a_value_written_in_is_unknown() -> None:
    # x = 10 writes "a|", but not with the text x = 1 wrote
    path = (
        fork([">", "x", 3], taken=True),
        fork(["startswith", hex_of("x", 1), "'a|'"], taken=True),
    )

    answer = solve(path, {"x": int, "y": int}, 5.0, values={"x": 1, "y": 0})

    assert answer == Unknown()


@needs_cvc5
def test_a_sat_keeps_a_value_written_in_where_it_was() -> None:
    path = (fork(["==", hex_of("x", 1), "'1|5'"], taken=True),)

    answer = solve(path, {"x": int, "y": int}, 5.0, values={"x": 1, "y": 0})

    assert isinstance(answer, Sat), answer
    assert answer.model.get("x", 1) == 1
    assert answer.model["y"] == 5


@needs_cvc5
@pytest.mark.parametrize(
    ("name", "value", "kind"),
    [("b", True, bool), ("s", "'ab'", str), ("f", float("nan"), float), ("f", -0.0, float)],
)
def test_each_kind_of_value_written_in_stays_exactly_as_it_was(
    name: str, value: Expression, kind: type
) -> None:
    path = (fork(["==", hex_of(name, value), "'1|5'"], taken=True),)

    answer = solve(path, {name: kind, "y": int}, 5.0)

    assert isinstance(answer, Sat), answer


@needs_cvc5
def test_an_unsat_beside_a_value_written_in_is_the_path_s() -> None:
    path = (
        fork(["==", hex_of("x", 1), "'1|0'"], taken=False),
        fork([">", "y", 3], taken=True),
        fork(["<", "y", 2], taken=True),
    )

    assert solve(path, {"x": int, "y": int}, 5.0) == Unsat()


def test_a_value_written_in_is_held_once_named_for_a_core_and_never_freed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, "unsat\n", f"unsat\n(\n{STAYS_NAME}0\n)\n")
    monkeypatch.setenv("PATH", str(tmp_path))
    path = (
        fork(["==", hex_of("x", 1), "'1|0'"], taken=True),
        fork(["startswith", hex_of("x", 1), "'a|'"], taken=True),
    )

    assert solve(path, {"x": int, "y": int}, 5.0) == Unknown()

    first, cored = asked(tmp_path)
    assert first.count("(assert (= |arg.x| 1))") == 1
    assert cored[0] == "(set-option :dump-unsat-cores true)"
    assert [line for line in cored if STAYS_NAME in line] == [
        f"(assert (! (= |arg.x| 1) :named {STAYS_NAME}0))"
    ]


def test_a_sat_with_a_value_written_in_asks_no_core(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, f"sat\n((|arg.y| 5))\n{NOT_UNKNOWN}")
    monkeypatch.setenv("PATH", str(tmp_path))

    answer = solve((fork(["==", hex_of("x", 1), "'1|5'"], taken=True),), {"x": int, "y": int}, 5.0)

    assert answer == Sat({"y": 5})
    assert len(asked(tmp_path)) == 1


def test_a_path_that_reads_no_result_written_in_holds_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, "unsat\n")
    monkeypatch.setenv("PATH", str(tmp_path))

    assert solve((fork([">", "x", 3], taken=True),), {"x": int}, 5.0) == Unsat()
    [program] = asked(tmp_path)
    assert not any("|arg.x| 1)" in line for line in program)
