"""A path on floats is asked finite first, and frees only the leaves an unsat rests on."""

import logging
import math
import shutil
from pathlib import Path

import pytest

from pyct.core.branch import Expression
from pyct.solver.answer import Error, Sat, Timeout, Unknown, Unsat
from pyct.solver.cvc5 import solve
from pyct.solver.floats import finite
from tests.unit.solver.test_cvc5 import NOT_UNKNOWN, fork

needs_cvc5 = pytest.mark.skipif(shutil.which("cvc5") is None, reason="cvc5 is not installed")

# a double's value as cvc5 prints it: 2.5, -1.0, and the quiet NaN
TWO_AND_A_HALF = f"(fp #b0 #b10000000000 #b01{'0' * 50})"
MINUS_ONE = f"(fp #b1 #b01111111111 #b{'0' * 52})"
NAN = f"(fp #b0 #b{'1' * 11} #b1{'0' * 51})"

# what cvc5 prints for an unsat when the program asks it to dump the core: the answer, then the
# names the unsat rests on, then its refusal of each question only a sat answers
UNSAT_ON_X = "unsat\n(\nfinite!arg.x\n)\n"
UNSAT_ON_NOTHING = "unsat\n(\n)\n"


def fake_cvc5(directory: Path, *answers: str) -> None:
    """A cvc5 that gives the answers in the order it is asked, one per ask.

    It keeps each program and its arguments, numbered in the order it was asked.
    """
    for n, answer in enumerate(answers):
        (directory / f"answer{n}").write_text(answer)
    script = directory / "cvc5"
    script.write_text(
        "#!/bin/sh\n"
        # PATH is the tmp directory while the test runs, so the script says where its tools are
        "PATH=/bin:/usr/bin\n"
        f'n=$(ls "{directory}" | grep -c "^program")\n'
        f'cat > "{directory}/program$n"\n'
        f'printf %s "$*" > "{directory}/argv$n"\n'
        f'cat "{directory}/answer$n"\n'
    )
    script.chmod(0o755)


def ask(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    prefix: tuple[Expression, ...] = ([">", "x", 2.5],),
    timeout: float = 10.0,
) -> object:
    """One solve of the prefix's conditions, each taken false, on float leaves x and y."""
    monkeypatch.setenv("PATH", str(tmp_path))
    forks = tuple(fork(condition, taken=False) for condition in prefix)
    return solve(forks, {"x": float, "y": float}, timeout)


def asked(tmp_path: Path) -> list[list[str]]:
    """The lines of each program the fake cvc5 was asked, in order."""
    count = len(list(tmp_path.glob("program*")))
    return [(tmp_path / f"program{n}").read_text().splitlines() for n in range(count)]


def held(name: str) -> str:
    """The assertion that holds one float leaf finite, as an ask that wants no core writes it."""
    return f"(assert {finite(f'|arg.{name}|')})"


def named(name: str) -> str:
    """The same assertion named for the leaf, so an unsat core can say it rests on it."""
    return f"(assert (! {finite(f'|arg.{name}|')} :named finite!arg.{name}))"


def test_a_float_path_is_asked_with_its_leaves_finite_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, f"sat\n((arg.x {TWO_AND_A_HALF}))\n{NOT_UNKNOWN}")

    assert ask(tmp_path, monkeypatch) == Sat({"x": 2.5})

    # a finite answer is the answer, so cvc5 is asked once, and for no core, which slows some
    # sat answers; y is on no fork, so nothing holds it
    [program] = asked(tmp_path)
    assert program[0] == "(set-logic ALL)"
    assert held("x") in program
    assert "y|" not in "\n".join(program)


def test_a_float_path_no_finite_double_takes_asks_for_the_core_then_frees_the_leaf(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, "unsat\n", UNSAT_ON_X, f"sat\n((arg.x {NAN}))\n{NOT_UNKNOWN}")

    answer = ask(tmp_path, monkeypatch)

    assert isinstance(answer, Sat)
    value = answer.model["x"]
    assert isinstance(value, float)
    assert math.isnan(value)
    first, cored, freed = asked(tmp_path)
    assert held("x") in first
    # the same leaves held, and the core asked for, only now that the first ask was unsat
    assert (cored[0], named("x") in cored) == ("(set-option :dump-unsat-cores true)", True)
    # nothing is left to hold finite, so the last ask is the path as it stands
    assert "fp.isNaN" not in "\n".join(freed)
    assert "dump-unsat-cores" not in "\n".join(freed)


def test_the_freed_ask_frees_only_the_leaves_the_unsat_rests_on(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sat = f"sat\n((arg.x {NAN}))\n((arg.y {MINUS_ONE}))\n{NOT_UNKNOWN}"
    fake_cvc5(tmp_path, "unsat\n", UNSAT_ON_X, sat)

    answer = ask(tmp_path, monkeypatch, (["==", "x", "x"], [">", "y", 0.0]))

    assert isinstance(answer, Sat)
    assert answer.model["y"] == -1.0
    first, cored, freed = asked(tmp_path)
    assert (held("x") in first, held("y") in first) == (True, True)
    assert (named("x") in cored, named("y") in cored) == (True, True)
    # the unsat rested on x being finite alone, so y is still held finite
    assert (held("x") in freed, held("y") in freed) == (False, True)


def test_an_unsat_that_rests_on_no_leaf_being_finite_is_the_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, "unsat\n", UNSAT_ON_NOTHING)

    assert ask(tmp_path, monkeypatch) == Unsat()
    # no double at all takes the path, so allowing more of them would ask for nothing
    assert len(asked(tmp_path)) == 2


def test_a_float_path_no_double_takes_is_unsat_once_every_leaf_is_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, "unsat\n", UNSAT_ON_X, "unsat\n")

    assert ask(tmp_path, monkeypatch) == Unsat()
    assert len(asked(tmp_path)) == 3


def test_an_ask_for_the_core_that_decides_nothing_is_the_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, "unsat\n", "unknown\n(:reason-unknown timeout)\n", "unsat\n")

    assert ask(tmp_path, monkeypatch) == Timeout()
    assert len(asked(tmp_path)) == 2


@pytest.mark.parametrize(
    ("first", "answer"),
    [
        ("unknown\n(:reason-unknown incomplete)\n", Unknown()),
        ("unknown\n(:reason-unknown timeout)\n", Timeout()),
        ('(error "parse error")\n', Error('(error "parse error")')),
    ],
    ids=["unknown", "timeout", "error"],
)
def test_a_finite_ask_that_decides_nothing_is_the_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, first: str, answer: object
) -> None:
    fake_cvc5(tmp_path, first, "unsat\n")

    assert ask(tmp_path, monkeypatch) == answer
    # only an unsat says no finite double takes the path, so only an unsat asks again
    assert len(asked(tmp_path)) == 1


def test_a_path_that_names_no_float_is_asked_once_as_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, "unsat\n")
    monkeypatch.setenv("PATH", str(tmp_path))

    # x is a float leaf, but the path names only n
    assert solve((fork(["<", "n", 3], taken=True),), {"n": int, "x": float}, 10.0) == Unsat()

    [program] = asked(tmp_path)
    assert program[0] == "(set-logic ALL)"
    assert "fp.isNaN" not in "\n".join(program)


def _clock(monkeypatch: pytest.MonkeyPatch, *readings: float) -> None:
    """The monotonic clock the solve reads, one reading per read.

    cvc5's own name for it is patched, so no other reader of the clock draws from these.
    """
    times = iter(readings)
    monkeypatch.setattr("pyct.solver.cvc5.monotonic", lambda: next(times))


def test_each_ask_after_the_first_gets_what_is_left_of_the_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unsat_on_y = "unsat\n(\nfinite!arg.y\n)\n"
    fake_cvc5(tmp_path, "unsat\n", UNSAT_ON_X, "unsat\n", unsat_on_y, "unsat\n")
    _clock(monkeypatch, 100.0, 101.0, 102.0, 103.0, 103.5)

    ask(tmp_path, monkeypatch, (["==", "x", "x"], [">", "y", 0.0]), timeout=5.0)

    # the first ask gets the whole limit, and each after it what is left before the deadline
    limits = [(tmp_path / f"argv{n}").read_text().split()[-1] for n in range(5)]
    assert limits == [
        "--tlimit-per=5000",
        "--tlimit-per=4000",
        "--tlimit-per=3000",
        "--tlimit-per=2000",
        "--tlimit-per=1500",
    ]


@pytest.mark.parametrize("asks", [1, 2], ids=["before-the-core", "before-the-freed-ask"])
def test_an_ask_with_no_time_left_is_a_timeout_without_cvc5(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, asks: int
) -> None:
    fake_cvc5(tmp_path, "unsat\n", UNSAT_ON_X, "unsat\n")
    _clock(monkeypatch, 100.0, *([101.0] * (asks - 1)), 105.0)

    with caplog.at_level(logging.DEBUG, logger="pyct.solver.cvc5"):
        assert ask(tmp_path, monkeypatch, timeout=5.0) == Timeout()

    assert len(asked(tmp_path)) == asks
    # every other timeout is logged where cvc5 is asked; this one asks nothing, so it says so
    assert caplog.records[-1].levelno == logging.DEBUG
    assert caplog.records[-1].getMessage() == "no time left to ask cvc5 again with more doubles"


@needs_cvc5
def test_the_real_cvc5_answers_a_finite_double_where_one_takes_the_path() -> None:
    # asked with every double allowed, cvc5 1.3.4 answers NaN for either side
    flips: list[Expression] = [[">", "x", 0.0], ["<", "x", 10.0]]
    for expression in flips:
        answer = solve((fork(expression, taken=False),), {"x": float}, 10.0)

        assert isinstance(answer, Sat)
        value = answer.model["x"]
        assert isinstance(value, float)
        assert math.isfinite(value)


@needs_cvc5
def test_the_real_cvc5_answers_nan_or_infinity_where_no_finite_double_takes_the_path() -> None:
    unequal = solve((fork(["!=", "x", "x"], taken=True),), {"x": float}, 10.0)
    beyond = solve((fork([">", "x", 1.7976931348623157e308], taken=True),), {"x": float}, 10.0)

    assert isinstance(unequal, Sat)
    assert isinstance(beyond, Sat)
    assert repr(unequal.model["x"]) == "nan"
    assert beyond.model["x"] == math.inf


@needs_cvc5
def test_the_real_cvc5_keeps_a_leaf_finite_beside_one_only_nan_serves() -> None:
    # `if x != x:` taken, then `if y > 0.0:` flipped: freed together, cvc5 answers NaN for both
    path = (fork(["!=", "x", "x"], taken=True), fork([">", "y", 0.0], taken=False))

    answer = solve(path, {"x": float, "y": float}, 10.0)

    assert isinstance(answer, Sat)
    x, y = answer.model["x"], answer.model["y"]
    assert isinstance(x, float) and isinstance(y, float)
    assert math.isnan(x)
    assert math.isfinite(y)
    assert not y > 0.0
