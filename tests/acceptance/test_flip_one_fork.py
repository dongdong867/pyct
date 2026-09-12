"""Acceptance tests for the flip-one-fork story, child run-the-second-input-and-print-its-line.

Each test spawns ``python -P -m pyct`` through the harness, the way the trace-the-seed
tests do: the second input is the solver's, so only a real run through the command line
proves pyct found cvc5, flipped the fork, and printed the line.
"""

from pathlib import Path

from tests.acceptance.harness import REPO_ROOT, run_pyct

ONE_CHECK = "targets.flip.one_check::classify"
ONE_CHECK_FILE = str(REPO_ROOT / "targets" / "flip" / "one_check.py")


# flip-one-fork-refuses-without-cvc5
def test_refuses_without_cvc5(tmp_path: Path) -> None:
    empty = str(tmp_path)

    result = run_pyct(ONE_CHECK, '{"x": 3}', path=empty)

    assert result.returncode == 1, result.stderr
    assert result.stdout == ""
    assert "cvc5" in result.stderr
    assert "not found" in result.stderr
    assert empty in result.stderr
    assert "install" in result.stderr
