"""Acceptance tests for the move-on-from-a-fork-the-solver-cannot-answer story.

Each test spawns ``python -P -m pyct`` through the harness and times the run by the
monotonic clock, because what the story promises is how long a run spends on a fork
cvc5 cannot answer. The ``order`` target has one: ``t <= s`` under ``s < t``, on two
tracked strings, which cvc5 1.3.4 does not answer even in 20 seconds.
"""

import subprocess
import time

from tests.acceptance.harness import (
    REPO_ROOT,
    input_lines,
    run_pyct,
    summary_line,
)

ORDER = "targets.flip.order::order"
ORDER_FILE = str(REPO_ROOT / "targets" / "flip" / "order.py")
# takes ``s < t`` and not ``t <= s``
SEED = '{"s": "a", "t": "b"}'
# ``if s < t:``, which cvc5 flips alone in milliseconds
OUTER = 2
# ``if t <= s:``, which cvc5 cannot answer while ``s < t`` holds; ``t`` starts at column 11
INNER = 3
INNER_COL = 11
INNER_MISSED = f"missed {ORDER_FILE}:{INNER}:{INNER_COL} timeout"
# ``return "not below"``, which only an input that takes ``s < t`` false runs
NOT_BELOW = 6


def timed(*argv: str, path: str | None = None) -> tuple[subprocess.CompletedProcess[str], float]:
    """One run through the command line, and the seconds it took by the monotonic clock."""
    started = time.monotonic()
    result = run_pyct(*argv, path=path)
    return result, time.monotonic() - started


def misses_of(stdout: str) -> list[tuple[int, str]]:
    """Each fork the summary line lists under ``misses``, as its line and why."""
    misses = summary_line(stdout)["misses"]
    assert isinstance(misses, list), stdout
    return [(int(miss["line"]), str(miss["why"])) for miss in misses]


def forks_of(line: dict[str, object]) -> list[tuple[int, bool]]:
    """Each fork one input took, as its line and the side taken."""
    forks = line["forks"]
    assert isinstance(forks, list), line
    return [(int(fork["line"]), bool(fork["taken"])) for fork in forks]


def covered_of(line: dict[str, object]) -> list[int]:
    """The lines of the ``order`` target one input ran."""
    covered = line["covered"]
    assert isinstance(covered, dict), line
    return [int(number) for number in covered.get(ORDER_FILE, [])]


def assert_it_went_on(result: subprocess.CompletedProcess[str]) -> None:
    """The miss on stderr, then a solver input that took ``s < t`` false and ran ``not below``."""
    trace = result.stderr.splitlines()
    assert INNER_MISSED in trace, result.stderr
    heads = [at for at, line in enumerate(trace) if line.startswith("solver {")]
    # the miss prints the moment its answer comes in, so an input after it is a later one
    assert heads and heads[0] > trace.index(INNER_MISSED), result.stderr
    went_on = [
        line
        for line in input_lines(result.stdout)
        if line["source"] == "solver"
        and (OUTER, False) in forks_of(line)
        and NOT_BELOW in covered_of(line)
    ]
    assert went_on, result.stdout


# move-on-from-a-fork-the-solver-cannot-answer-goes-on-after-a-timeout
def test_goes_on_after_a_timeout() -> None:
    result, elapsed = timed(ORDER, SEED, "--solver-timeout", "1")

    assert result.returncode == 0, result.stderr
    assert_it_went_on(result)
    summary = summary_line(result.stdout)
    solver = summary["solver"]
    assert isinstance(solver, dict), summary
    assert solver["timeout"] == 1, summary
    assert summary["misses"] == [
        {"file": ORDER_FILE, "line": INNER, "col": INNER_COL, "why": "timeout"}
    ], summary
    assert summary["stopped"] == "no fork to flip", summary
    assert elapsed < 10, elapsed


# move-on-from-a-fork-the-solver-cannot-answer-waits-ten-seconds-by-default
def test_waits_ten_seconds_by_default() -> None:
    result, elapsed = timed(ORDER, SEED)

    assert result.returncode == 0, result.stderr
    assert (INNER, "timeout") in misses_of(result.stdout), result.stdout
    assert summary_line(result.stdout)["stopped"] == "no fork to flip", result.stdout
    # the one solve cvc5 cannot answer takes the whole default limit, and nothing else is slow
    assert 10 <= elapsed <= 20, elapsed


# move-on-from-a-fork-the-solver-cannot-answer-keeps-to-the-budget
def test_keeps_to_the_budget() -> None:
    result, elapsed = timed(ORDER, SEED, "--budget", "2", "--solver-timeout", "30")

    assert result.returncode == 0, result.stderr
    assert (INNER, "timeout") in misses_of(result.stdout), result.stdout
    assert summary_line(result.stdout)["stopped"] == "budget spent", result.stdout
    # the solve got what was left of the budget, not the 30 seconds the flag allows
    assert elapsed < 5, elapsed


# move-on-from-a-fork-the-solver-cannot-answer-goes-on-inside-a-budget
def test_goes_on_inside_a_budget() -> None:
    result, elapsed = timed(ORDER, SEED, "--budget", "30", "--solver-timeout", "1")

    assert result.returncode == 0, result.stderr
    assert (INNER, "timeout") in misses_of(result.stdout), result.stdout
    assert_it_went_on(result)
    assert summary_line(result.stdout)["stopped"] == "no fork to flip", result.stdout
    # the solve got the flag's second, not the 30 the budget had left
    assert elapsed < 10, elapsed


# move-on-from-a-fork-the-solver-cannot-answer-refuses-a-bad-limit
def test_refuses_a_bad_limit() -> None:
    for bad in ["0", "-1", "nan", "inf", "abc"]:
        result = run_pyct(ORDER, SEED, "--solver-timeout", bad)

        assert result.returncode == 2, bad
        assert result.stdout == "", bad
        # the refusal alone, with no trace: the flags are read before the target is imported
        lines = result.stderr.splitlines()
        assert len(lines) == 1, result.stderr
        assert "solver timeout" in lines[0], result.stderr
        assert repr(bad) in lines[0], result.stderr
