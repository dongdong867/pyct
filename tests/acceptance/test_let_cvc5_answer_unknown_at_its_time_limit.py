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
    """A cvc5 that runs the real one and writes down each call's start and end. Returns the PATH.

    A shell reads a call that a signal ended as 128 plus the signal's number,
    so the status it writes down tells an answer from a signal. A call pyct
    stops ends the script too, so that call has a start and no end.
    """
    real = shutil.which("cvc5")
    assert real is not None, "the real cvc5 is not on PATH"
    calls = tmp_path / "calls"
    script = tmp_path / "cvc5"
    script.write_text(
        "#!/bin/sh\n"
        f'echo "start $$ $1" >> "{calls}"\n'
        f'"{real}" "$@"\n'
        "status=$?\n"
        f'echo "end $$ $status" >> "{calls}"\n'
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


def records(tmp_path: Path, kind: str) -> dict[str, str]:
    """What the recording cvc5 wrote at each call's ``start`` or ``end``, by the call's process.

    A start holds the call's first argument, and an end its exit status.
    """
    lines = (tmp_path / "calls").read_text().splitlines()
    fields = [line.split(" ", 2) for line in lines]
    return {process: value for said, process, value in fields if said == kind}


def assert_no_signal(tmp_path: Path) -> None:
    """Every cvc5 call that started exited 0, and at least one was a solve, not the check."""
    started = records(tmp_path, "start")
    assert records(tmp_path, "end") == dict.fromkeys(started, "0"), started
    assert any(first != "--version" for first in started.values()), started


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
