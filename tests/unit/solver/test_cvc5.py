import logging
import shutil
import time
from pathlib import Path

import pytest

from pyct.core.branch import Branch, Expression, Site
from pyct.solver.answer import Error, Sat, Timeout, Unknown, Unsat
from pyct.solver.cvc5 import GRACE_SECONDS, solve

SITE = Site(file="m.py", line=2, col=7)


def fork(expression: Expression, *, taken: bool) -> Branch:
    """A fork at one fixed site: only the condition and the side matter here."""
    return Branch(expression=expression, taken=taken, site=SITE)


def fake_cvc5(directory: Path, *, out: str = "", err: str = "", code: int = 0) -> None:
    """A cvc5 that reads the formula, says what the test wants, and records its arguments."""
    (directory / "out").write_text(out)
    (directory / "err").write_text(err)
    script = directory / "cvc5"
    script.write_text(
        "#!/bin/sh\n"
        # PATH is the tmp directory while the test runs, so the script says where its tools are
        "PATH=/bin:/usr/bin\n"
        "cat > /dev/null\n"
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
    fake_cvc5(tmp_path, out="sat\n((x 12))\n")

    assert ask(tmp_path, monkeypatch) == Sat({"x": 12})


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


def test_a_solver_that_ran_out_of_time_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, err="cvc5 interrupted by timeout.\n", code=134)

    assert ask(tmp_path, monkeypatch) == Timeout()


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

    assert "--tlimit=1500" in (tmp_path / "argv").read_text()


def test_a_solver_that_runs_past_its_limit_is_stopped_as_a_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    script = tmp_path / "cvc5"
    # it reads the formula and ignores --tlimit; exec lets stopping the script stop the sleep
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
    assert "stopped cvc5" in warnings[0].getMessage()


@pytest.mark.skipif(shutil.which("cvc5") is None, reason="cvc5 is not installed")
def test_the_real_cvc5_answers_both_ways() -> None:
    reachable = solve((fork(["<", "x", 10], taken=False),), {"x": int}, 10.0)
    assert isinstance(reachable, Sat)
    value = reachable.model["x"]
    assert isinstance(value, int)
    assert value >= 10

    contradiction = (fork(["<", "x", 5], taken=True), fork(["<", "x", 10], taken=False))
    assert solve(contradiction, {"x": int}, 10.0) == Unsat()
