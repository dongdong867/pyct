"""Acceptance tests for the report-an-exit-or-crash-at-import bug.

Each test spawns ``python -P -m pyct`` through the harness, because an exit or a crash at
import ends the process that imports the target, and only a real run shows what the shell
that started pyct gets back.
"""

import signal
from pathlib import Path

import pytest

from tests.acceptance.harness import input_lines, run_pyct

EXITS = "targets.load.exits_at_import"
EXITS_CLEANLY = "targets.load.exits_cleanly_at_import"
ENDS_ITS_PROCESS = "targets.load.ends_its_process_at_import"
CRASHES = "targets.load.crashes_at_import"
INTERRUPTED = "targets.load.interrupted_at_import"
COUNTS_ITS_IMPORTS = "targets.load.counts_its_imports"


def outcome(module: str) -> tuple[str, int, str]:
    """What stdout, the exit code and stderr say when pyct runs ``f`` in ``module``."""
    result = run_pyct(f"{module}::f", "--args", '{"x": 1}')
    return result.stdout, result.returncode, result.stderr


# report-an-exit-or-crash-at-import-names-an-exit
def test_names_an_exit() -> None:
    stdout, code, stderr = outcome(EXITS)

    assert stderr.splitlines() == [f"cannot import {EXITS}: SystemExit(4)"]
    assert stdout == ""
    assert code == 1


# report-an-exit-or-crash-at-import-refuses-a-clean-exit
def test_refuses_a_clean_exit() -> None:
    stdout, code, stderr = outcome(EXITS_CLEANLY)

    assert stderr.splitlines() == [f"cannot import {EXITS_CLEANLY}: SystemExit()"]
    assert stdout == ""
    assert code == 1


# report-an-exit-or-crash-at-import-names-a-process-exit
def test_names_a_process_exit() -> None:
    stdout, code, stderr = outcome(ENDS_ITS_PROCESS)

    assert stderr.splitlines() == [f"cannot import {ENDS_ITS_PROCESS}: exited with code 3"]
    assert stdout == ""
    assert code == 1


# report-an-exit-or-crash-at-import-names-a-crash
def test_names_a_crash() -> None:
    stdout, code, stderr = outcome(CRASHES)

    assert stderr.splitlines() == [f"cannot import {CRASHES}: killed by SIGSEGV"]
    assert stdout == ""
    assert code == 1


# the ticket's Keep: a KeyboardInterrupt at import ends pyct as a Ctrl-C always has
def test_ends_as_a_ctrl_c_does_on_a_keyboard_interrupt_at_import() -> None:
    stdout, code, stderr = outcome(INTERRUPTED)

    assert code == -signal.SIGINT, stderr
    assert stderr.splitlines()[-1] == "KeyboardInterrupt"
    assert "cannot import" not in stderr
    assert stdout == ""


# the ticket's Keep: the module is still imported once per run, in the process that runs it
def test_imports_the_module_once_per_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    notes = tmp_path / "imports"
    monkeypatch.setenv("PYCT_TEST_IMPORTS", str(notes))

    result = run_pyct(f"{COUNTS_ITS_IMPORTS}::f", "--args", '{"x": 0}')

    assert result.returncode == 0, result.stderr
    assert len(input_lines(result.stdout)) == 2, result.stdout
    assert len(notes.read_text().splitlines()) == 1
