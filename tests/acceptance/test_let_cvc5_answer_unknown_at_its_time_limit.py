"""Acceptance tests for the let-cvc5-answer-unknown-at-its-time-limit bug.

Each test spawns ``python -P -m pyct`` through the harness with a cvc5 of its own
first on PATH. The ``order`` target has a fork cvc5 cannot answer: ``t <= s`` under
``s < t``, on two tracked strings, so its solve always reaches its time limit. What
the bug promises is how that solve ends: cvc5 answers, rather than a signal ending it,
and the fork is still a ``timeout`` miss.
"""

import os
import shutil
from pathlib import Path

from tests.acceptance.harness import REPO_ROOT, run_pyct, summary_line

ORDER = "targets.flip.order::order"
ORDER_FILE = str(REPO_ROOT / "targets" / "flip" / "order.py")
# takes ``s < t`` and not ``t <= s``
SEED = '{"s": "a", "t": "b"}'
# ``if s < t:``, which cvc5 flips alone in milliseconds
OUTER = 2
# ``if t <= s:``, which cvc5 cannot answer while ``s < t`` holds; ``t`` starts at column 11
INNER = 3
INNER_COL = 11


def recording_cvc5(tmp_path: Path) -> str:
    """A cvc5 that runs the real one and writes down how each call ended. Returns the PATH.

    A shell reads a call that a signal ended as 128 plus the signal's number,
    so the status it writes down tells an answer from a signal.
    """
    real = shutil.which("cvc5")
    assert real is not None, "the real cvc5 is not on PATH"
    script = tmp_path / "cvc5"
    script.write_text(
        "#!/bin/sh\n"
        f'"{real}" "$@"\n'
        "status=$?\n"
        f'echo "$status $1" >> "{tmp_path / "ended"}"\n'
        'exit "$status"\n'
    )
    script.chmod(0o755)
    return f"{tmp_path}{os.pathsep}{os.environ['PATH']}"


def unknown_cvc5(tmp_path: Path) -> str:
    """A cvc5 that answers every formula at once with ``unknown``, ``incomplete`` when asked why.

    It says its version at once, so pyct's check passes. Returns the PATH.
    """
    script = tmp_path / "cvc5"
    script.write_text(
        "#!/bin/sh\n"
        # PATH is the tmp directory while the test runs, so the script says where its tools are
        "PATH=/bin:/usr/bin\n"
        'if [ "$1" = "--version" ]; then\n'
        "    echo 'cvc5 1.3.4'\n"
        "    exit 0\n"
        "fi\n"
        'program="$(cat)"\n'
        "echo unknown\n"
        'case "$program" in\n'
        "    *'(get-info :reason-unknown)'*) echo '(:reason-unknown incomplete)' ;;\n"
        "esac\n"
    )
    script.chmod(0o755)
    return str(tmp_path)


def statuses(tmp_path: Path) -> list[tuple[int, str]]:
    """Each call the recording cvc5 saw, as its exit status and its first argument."""
    lines = (tmp_path / "ended").read_text().splitlines()
    return [(int(status), first) for status, first in (line.split(" ", 1) for line in lines)]


def assert_no_signal(tmp_path: Path) -> None:
    """Every cvc5 call exited 0, and at least one of them was a solve rather than the check."""
    ended = statuses(tmp_path)
    assert [status for status, _ in ended] == [0] * len(ended), ended
    assert any(first != "--version" for _, first in ended), ended


def misses_of(stdout: str) -> list[tuple[int, str]]:
    """Each fork the summary line lists under ``misses``, as its line and why."""
    misses = summary_line(stdout)["misses"]
    assert isinstance(misses, list), stdout
    return [(int(miss["line"]), str(miss["why"])) for miss in misses]


# let-cvc5-answer-unknown-at-its-time-limit-ends-a-solve-without-a-signal
def test_ends_a_solve_without_a_signal(tmp_path: Path) -> None:
    path = recording_cvc5(tmp_path)

    result = run_pyct(ORDER, SEED, "--solver-timeout", "1", path=path)

    assert result.returncode == 0, result.stderr
    assert f"missed {ORDER_FILE}:{INNER}:{INNER_COL} timeout" in result.stderr.splitlines()
    solver = summary_line(result.stdout)["solver"]
    assert isinstance(solver, dict), result.stdout
    assert (solver["timeout"], solver["unknown"]) == (1, 0), solver
    assert_no_signal(tmp_path)


# let-cvc5-answer-unknown-at-its-time-limit-ends-a-budget-cut-solve-without-a-signal
def test_ends_a_budget_cut_solve_without_a_signal(tmp_path: Path) -> None:
    path = recording_cvc5(tmp_path)

    result = run_pyct(ORDER, SEED, "--budget", "2", "--solver-timeout", "30", path=path)

    assert result.returncode == 0, result.stderr
    assert (INNER, "timeout") in misses_of(result.stdout), result.stdout
    assert summary_line(result.stdout)["stopped"] == "budget spent", result.stdout
    assert_no_signal(tmp_path)


# let-cvc5-answer-unknown-at-its-time-limit-keeps-a-plain-unknown
def test_keeps_a_plain_unknown(tmp_path: Path) -> None:
    path = unknown_cvc5(tmp_path)

    result = run_pyct(ORDER, SEED, path=path)

    assert result.returncode == 0, result.stderr
    # nothing is ever answered: both forks are aimed at, and both are misses
    assert sorted(misses_of(result.stdout)) == [(OUTER, "unknown"), (INNER, "unknown")]
    solver = summary_line(result.stdout)["solver"]
    assert solver == {"sat": 0, "unsat": 0, "unknown": 2, "timeout": 0}, solver
