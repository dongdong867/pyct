import shutil
from pathlib import Path

import pytest

from pyct.core.branch import Branch, Expression, Site
from pyct.solver.answer import Error, Sat, Timeout, Unknown, Unsat
from pyct.solver.cvc5 import solve

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


def ask(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, timeout: float | None = None) -> object:
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


def test_a_timeout_is_passed_to_the_solver_in_milliseconds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, out="unsat\n")

    ask(tmp_path, monkeypatch, timeout=1.5)

    assert "--tlimit=1500" in (tmp_path / "argv").read_text()


def test_no_timeout_leaves_the_solver_unlimited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_cvc5(tmp_path, out="unsat\n")

    ask(tmp_path, monkeypatch, timeout=None)

    assert "--tlimit" not in (tmp_path / "argv").read_text()


@pytest.mark.skipif(shutil.which("cvc5") is None, reason="cvc5 is not installed")
def test_the_real_cvc5_answers_both_ways() -> None:
    reachable = solve((fork(["<", "x", 10], taken=False),), {"x": int}, None)
    assert isinstance(reachable, Sat)
    value = reachable.model["x"]
    assert isinstance(value, int)
    assert value >= 10

    contradiction = (fork(["<", "x", 5], taken=True), fork(["<", "x", 10], taken=False))
    assert solve(contradiction, {"x": int}, None) == Unsat()
