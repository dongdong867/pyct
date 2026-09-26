import json
import logging
import math
import shutil
import time
from pathlib import Path

import pytest

from pyct.core.branch import Branch, Expression, Site
from pyct.solver.answer import Error, Sat, SolverAnswerError, Timeout, Unknown, Unsat
from pyct.solver.cvc5 import GRACE_SECONDS, solve

SITE = Site(file="m.py", line=2, col=7)

# what cvc5 prints when asked why after an answer that is not unknown
NOT_UNKNOWN = "(error \"Can't get-info :reason-unknown when the last result wasn't unknown!\")\n"


def fork(expression: Expression, *, taken: bool) -> Branch:
    """A fork at one fixed site: only the condition and the side matter here."""
    return Branch(expression=expression, taken=taken, site=SITE)


def fake_cvc5(directory: Path, *, out: str = "", err: str = "", code: int = 0) -> None:
    """A cvc5 that keeps the formula, says what the test wants, and records its arguments."""
    (directory / "out").write_text(out)
    (directory / "err").write_text(err)
    script = directory / "cvc5"
    script.write_text(
        "#!/bin/sh\n"
        # PATH is the tmp directory while the test runs, so the script says where its tools are
        "PATH=/bin:/usr/bin\n"
        f'cat > "{directory}/program"\n'
        f'printf %s "$*" > "{directory}/argv"\n'
        f'cat "{directory}/out"\n'
        f'cat "{directory}/err" >&2\n'
        f"exit {code}\n"
    )
    script.chmod(0o755)


def ask(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timeout: float = 10.0) -> object:
    """One solve of the one-fork path, against whatever cvc5 the tmp directory holds."""
    monkeypatch.setenv("PATH", str(tmp_path))
    return solve((fork(["<", "x", 10], taken=False),), {"x": int}, timeout)


def test_a_solved_path_comes_back_with_its_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, out=f"sat\n((arg.x 12))\n{NOT_UNKNOWN}")

    assert ask(tmp_path, monkeypatch) == Sat({"x": 12})


@pytest.mark.parametrize(
    "out",
    [
        # the reply is missing, so the last line may be a value rather than the reply
        "sat\n((x 12))\n((y 3))\n",
        # a reason is no reply to a sat, which leaves no reason to ask about
        "sat\n((x 12))\n(:reason-unknown timeout)\n",
    ],
)
def test_a_sat_without_its_reply_to_why_is_an_error_rather_than_a_lost_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, out: str
) -> None:
    fake_cvc5(tmp_path, out=out)

    answer = ask(tmp_path, monkeypatch)

    assert isinstance(answer, Error), answer
    assert answer.detail == out.strip()


def test_a_path_nothing_reaches_comes_back_unsat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, out="unsat\n")

    assert ask(tmp_path, monkeypatch) == Unsat()


def test_a_path_the_solver_gave_up_on_comes_back_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, out="unknown\n")

    assert ask(tmp_path, monkeypatch) == Unknown()


def test_an_unknown_for_a_reason_other_than_time_stays_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, out="unknown\n((x 0))\n(:reason-unknown incomplete)\n")

    assert ask(tmp_path, monkeypatch) == Unknown()


def test_an_unknown_because_the_time_ran_out_is_a_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # how cvc5 ends a check at --tlimit-per: it answers and exits 0, rather than aborting
    fake_cvc5(tmp_path, out="unknown\n((x 0))\n(:reason-unknown timeout)\n")

    assert ask(tmp_path, monkeypatch) == Timeout()


def test_the_solver_is_asked_why_after_everything_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, out="unsat\n")

    ask(tmp_path, monkeypatch)

    program = (tmp_path / "program").read_text().splitlines()
    assert program[-1] == "(get-info :reason-unknown)", program
    assert "(check-sat)" in program[:-1], program


def test_anything_else_is_an_error_that_keeps_what_the_solver_said(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, out='(error "parse error")\n', code=1)

    answer = ask(tmp_path, monkeypatch)

    assert isinstance(answer, Error)
    assert "parse error" in answer.detail


def test_a_solver_that_failed_to_answer_is_warned_about(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    fake_cvc5(tmp_path, out='(error "parse error")\n', code=1)

    with caplog.at_level(logging.WARNING, logger="pyct.solver.cvc5"):
        ask(tmp_path, monkeypatch)

    # the solver only warns; the run decides the failure is fatal
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, caplog.text
    assert "parse error" in warnings[0].getMessage()


def test_a_timeout_is_passed_to_the_solver_in_milliseconds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, out="unsat\n")

    ask(tmp_path, monkeypatch, timeout=1.5)

    assert "--tlimit-per=1500" in (tmp_path / "argv").read_text().split()


def test_a_limit_under_a_millisecond_reaches_the_solver_as_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, out="unsat\n")

    # a nearly spent budget gives a limit like this; cvc5 reads --tlimit-per=0 as no limit
    ask(tmp_path, monkeypatch, timeout=0.0001)

    assert "--tlimit-per=1" in (tmp_path / "argv").read_text().split()


def test_a_limit_longer_than_python_can_wait_is_cut_to_the_longest_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, out="unsat\n")

    # about 115 days, past the 2**31 - 1 milliseconds Python's poll can wait
    assert ask(tmp_path, monkeypatch, timeout=1e7) == Unsat()

    # cut to that wait in whole seconds, less the grace second, and no shorter
    assert "--tlimit-per=2147482000" in (tmp_path / "argv").read_text().split()


def test_a_solver_that_runs_past_its_limit_is_stopped_as_a_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    script = tmp_path / "cvc5"
    # it reads the formula and ignores its limit; exec lets stopping the script stop the sleep
    script.write_text("#!/bin/sh\nPATH=/bin:/usr/bin\ncat > /dev/null\nexec sleep 3600\n")
    script.chmod(0o755)

    started = time.monotonic()
    with caplog.at_level(logging.WARNING, logger="pyct.solver.cvc5"):
        answer = ask(tmp_path, monkeypatch, timeout=0.1)
    elapsed = time.monotonic() - started

    assert answer == Timeout()
    # pyct gives it the limit and the grace, then stops it, instead of waiting on the sleep
    assert 0.1 + GRACE_SECONDS <= elapsed < 0.1 + GRACE_SECONDS + 1.0, elapsed
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1, caplog.text
    # the command line holds the limit, so the warning does not repeat it
    assert warnings[0].getMessage() == "pyct stopped cvc5, which ran past its time limit"


@pytest.mark.skipif(shutil.which("cvc5") is None, reason="cvc5 is not installed")
def test_the_real_cvc5_answers_both_ways() -> None:
    reachable = solve((fork(["<", "x", 10], taken=False),), {"x": int}, 10.0)
    assert isinstance(reachable, Sat)
    value = reachable.model["x"]
    assert isinstance(value, int)
    assert value >= 10

    contradiction = (fork(["<", "x", 5], taken=True), fork(["<", "x", 10], taken=False))
    assert solve(contradiction, {"x": int}, 10.0) == Unsat()


@pytest.mark.skipif(shutil.which("cvc5") is None, reason="cvc5 is not installed")
def test_the_real_cvc5_says_when_it_ran_out_of_time() -> None:
    # s < t and t <= s on strings, which cvc5 1.3.4 does not answer even in 20 seconds
    unanswerable = (fork(["<", "s", "t"], taken=True), fork(["<=", "t", "s"], taken=True))

    started = time.monotonic()
    answer = solve(unanswerable, {"s": str, "t": str}, 0.2)

    assert answer == Timeout()
    # cvc5 stopped itself at its limit; pyct's own stop would have taken the grace too
    assert time.monotonic() - started < 0.2 + GRACE_SECONDS, answer


@pytest.mark.skipif(shutil.which("cvc5") is None, reason="cvc5 is not installed")
def test_the_real_cvc5_answers_about_a_value_inside_by_its_access() -> None:
    # a key holding the two characters no SMT-LIB symbol can, `|` and a backslash
    access: Expression = ["[]", "d", repr("a|b\\c")]
    name = json.dumps(access)

    answer = solve((fork(["<", access, 1], taken=True),), {"x": int, name: int}, 10.0)

    assert isinstance(answer, Sat)
    assert list(answer.model) == [name]
    value = answer.model[name]
    assert isinstance(value, int) and value < 1


@pytest.mark.skipif(shutil.which("cvc5") is None, reason="cvc5 is not installed")
def test_the_real_cvc5_answers_about_parameters_named_as_its_own_words_or_past_ascii() -> None:
    path = (fork([">", "div", 3], taken=True), fork(["==", "café", "'é'"], taken=True))

    answer = solve(path, {"div": int, "café": str}, 10.0)

    assert isinstance(answer, Sat)
    assert answer.model["café"] == "é"
    value = answer.model["div"]
    assert isinstance(value, int) and value > 3


def test_a_model_naming_what_was_not_declared_is_an_error_rather_than_a_guess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, out=f"sat\n((arg.y 12))\n{NOT_UNKNOWN}")

    with pytest.raises(SolverAnswerError, match="arg.y"):
        ask(tmp_path, monkeypatch)


# a double's value as cvc5 prints it: 2.5, and the quiet NaN
TWO_AND_A_HALF = f"(fp #b0 #b10000000000 #b01{'0' * 50})"
NAN = f"(fp #b0 #b{'1' * 11} #b1{'0' * 51})"


def fake_float_cvc5(directory: Path, *, finite: str, full: str) -> None:
    """A cvc5 that answers ``finite`` to a program holding a leaf finite, and ``full`` to any
    other. It keeps each program and its arguments, numbered in the order it was asked.
    """
    (directory / "finite").write_text(finite)
    (directory / "full").write_text(full)
    script = directory / "cvc5"
    script.write_text(
        "#!/bin/sh\n"
        "PATH=/bin:/usr/bin\n"
        f'n=$(ls "{directory}" | grep -c "^program")\n'
        f'cat > "{directory}/program$n"\n'
        f'printf %s "$*" > "{directory}/argv$n"\n'
        f'if grep -q fp.isNaN "{directory}/program$n"; then cat "{directory}/finite";'
        f' else cat "{directory}/full"; fi\n'
    )
    script.chmod(0o755)


def ask_float(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timeout: float = 10.0) -> object:
    """One solve of a one-fork path on a float, against whatever cvc5 the tmp directory holds."""
    monkeypatch.setenv("PATH", str(tmp_path))
    return solve((fork([">", "x", 2.5], taken=False),), {"x": float}, timeout)


def asked(tmp_path: Path) -> list[str]:
    """Each program the fake cvc5 was asked, in order."""
    return [(tmp_path / f"program{n}").read_text() for n in range(len(programs(tmp_path)))]


def programs(tmp_path: Path) -> list[Path]:
    return sorted(tmp_path.glob("program*"))


def test_a_float_path_is_asked_with_its_leaves_finite_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_float_cvc5(tmp_path, finite=f"sat\n((arg.x {TWO_AND_A_HALF}))\n{NOT_UNKNOWN}", full="")

    assert ask_float(tmp_path, monkeypatch) == Sat({"x": 2.5})

    # a finite answer is the answer, so cvc5 is asked once
    [program] = asked(tmp_path)
    assert "(assert (not (or (fp.isNaN |arg.x|) (fp.isInfinite |arg.x|))))" in program.splitlines()


def test_a_float_path_no_finite_double_takes_is_asked_again_with_every_double(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_float_cvc5(tmp_path, finite="unsat\n", full=f"sat\n((arg.x {NAN}))\n{NOT_UNKNOWN}")

    answer = ask_float(tmp_path, monkeypatch)

    assert isinstance(answer, Sat)
    value = answer.model["x"]
    assert isinstance(value, float)
    assert math.isnan(value)
    first, second = asked(tmp_path)
    assert "fp.isNaN" in first
    assert "fp.isNaN" not in second


def test_a_float_path_no_double_takes_is_unsat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_float_cvc5(tmp_path, finite="unsat\n", full="unsat\n")

    assert ask_float(tmp_path, monkeypatch) == Unsat()
    assert len(asked(tmp_path)) == 2


@pytest.mark.parametrize(
    ("finite", "answer"),
    [
        ("unknown\n(:reason-unknown incomplete)\n", Unknown()),
        ("unknown\n(:reason-unknown timeout)\n", Timeout()),
        ('(error "parse error")\n', Error('(error "parse error")')),
    ],
    ids=["unknown", "timeout", "error"],
)
def test_a_finite_ask_that_decides_nothing_is_the_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, finite: str, answer: object
) -> None:
    fake_float_cvc5(tmp_path, finite=finite, full="unsat\n")

    assert ask_float(tmp_path, monkeypatch) == answer
    # only an unsat says no finite double takes the path, so only an unsat asks again
    assert len(asked(tmp_path)) == 1


def test_a_path_that_names_no_float_is_asked_once_as_it_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_float_cvc5(tmp_path, finite="", full="unsat\n")
    monkeypatch.setenv("PATH", str(tmp_path))

    # x is a float leaf, but the path names only n
    assert solve((fork(["<", "n", 3], taken=True),), {"n": int, "x": float}, 10.0) == Unsat()

    [program] = asked(tmp_path)
    assert "fp.isNaN" not in program


def _clock(monkeypatch: pytest.MonkeyPatch, *readings: float) -> None:
    """The monotonic clock the solve reads, one reading per read."""
    times = iter(readings)
    monkeypatch.setattr("pyct.solver.cvc5.time.monotonic", lambda: next(times))


def test_the_second_ask_gets_what_the_first_left_of_the_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_float_cvc5(tmp_path, finite="unsat\n", full="unsat\n")
    _clock(monkeypatch, 100.0, 103.5)

    ask_float(tmp_path, monkeypatch, timeout=5.0)

    assert "--tlimit-per=5000" in (tmp_path / "argv0").read_text().split()
    assert "--tlimit-per=1500" in (tmp_path / "argv1").read_text().split()


def test_a_second_ask_with_no_time_left_is_a_timeout_without_cvc5(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_float_cvc5(tmp_path, finite="unsat\n", full="unsat\n")
    _clock(monkeypatch, 100.0, 105.0)

    assert ask_float(tmp_path, monkeypatch, timeout=5.0) == Timeout()
    assert len(asked(tmp_path)) == 1


@pytest.mark.skipif(shutil.which("cvc5") is None, reason="cvc5 is not installed")
def test_the_real_cvc5_answers_a_finite_double_where_one_takes_the_path() -> None:
    # asked with every double allowed, cvc5 1.3.4 answers NaN for either side
    flips: list[Expression] = [[">", "x", 0.0], ["<", "x", 10.0]]
    for expression in flips:
        answer = solve((fork(expression, taken=False),), {"x": float}, 10.0)

        assert isinstance(answer, Sat)
        value = answer.model["x"]
        assert isinstance(value, float)
        assert math.isfinite(value)


@pytest.mark.skipif(shutil.which("cvc5") is None, reason="cvc5 is not installed")
def test_the_real_cvc5_answers_nan_or_infinity_where_no_finite_double_takes_the_path() -> None:
    unequal = solve((fork(["!=", "x", "x"], taken=True),), {"x": float}, 10.0)
    beyond = solve((fork([">", "x", 1.7976931348623157e308], taken=True),), {"x": float}, 10.0)

    assert isinstance(unequal, Sat)
    assert isinstance(beyond, Sat)
    assert repr(unequal.model["x"]) == "nan"
    assert beyond.model["x"] == math.inf
