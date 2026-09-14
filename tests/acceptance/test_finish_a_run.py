"""Acceptance tests for the finish-a-run story, children print-the-summary-line
and loop-until-no-fork-is-left.

Each test spawns ``python -P -m pyct`` through the harness, the way the flip-one-fork
tests do: the summary line closes stdout after the last input line, so only a real run
through the command line proves the order it comes in and the environment it names.
"""

import platform
from pathlib import Path

from tests.acceptance.harness import (
    REPO_ROOT,
    crashing_cvc5,
    input_lines,
    run_pyct,
    summary_line,
)

ONE_CHECK = "targets.flip.one_check::classify"
NESTED_CHECKS = "targets.flip.nested_checks::bucket"
NESTED_CHECKS_FILE = str(REPO_ROOT / "targets" / "flip" / "nested_checks.py")
NO_CHECK = "targets.flip.no_check::echo"
UNFOLLOWED_GUARD = "targets.flip.unfollowed_guard::route"
UNFOLLOWED_GUARD_FILE = str(REPO_ROOT / "targets" / "flip" / "unfollowed_guard.py")
# ``return "never"``, behind the ``x >= 10`` guard pyct does not follow: the flip aims at
# the ``x < 10`` below it, lands inside the guard instead, and the line is never run
NEVER = 8
# every line of ``bucket`` but its ``def``, which runs at import rather than under an input
BUCKET_LINES = [2, 3, 4, 5, 6]
# no solver call ended any way at all
ZERO_ANSWERS = {"sat": 0, "unsat": 0, "unknown": 0, "timeout": 0}


def numbers_of(line: dict[str, object], key: str) -> dict[str, list[int]]:
    """One map of line numbers off a printed line, narrowed so a lookup means something."""
    payload = line[key]
    assert isinstance(payload, dict), line
    return {str(file): [int(number) for number in lines] for file, lines in payload.items()}


def union_of(lines: list[dict[str, object]]) -> dict[str, list[int]]:
    """Every input's covered map added up, written the way a printed line writes one."""
    union: dict[str, set[int]] = {}
    for line in lines:
        for file, covered in numbers_of(line, "covered").items():
            union[file] = union.get(file, set()) | set(covered)
    return {file: sorted(covered) for file, covered in union.items()}


# finish-a-run-covers-every-branch
def test_covers_every_branch() -> None:
    result = run_pyct(NESTED_CHECKS, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # the seed takes both checks; the other side of each is a way out of its own
    assert len(inputs) == 3, result.stdout
    assert union_of(inputs) == {NESTED_CHECKS_FILE: BUCKET_LINES}
    summary = summary_line(result.stdout)
    # nothing is left over but the ``def`` line no input can run
    assert numbers_of(summary, "uncovered") == {NESTED_CHECKS_FILE: [1]}
    assert summary["stopped"] == "no fork to flip"


# finish-a-run-prints-the-summary-line
def test_prints_the_summary_line() -> None:
    result = run_pyct(ONE_CHECK, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    summary = summary_line(result.stdout)
    # summary_line takes the last line and asserts the key; no input line carries it
    assert all("stopped" not in line for line in inputs), result.stdout
    assert len(inputs) == 2, result.stdout
    assert summary["inputs"] == len(inputs)
    # the run's coverage is every input's added up, and the module is the same size throughout
    assert summary["covered"] == union_of(inputs)
    assert all(line["total"] == summary["total"] for line in inputs), result.stdout
    environment = summary["environment"]
    assert isinstance(environment, dict), summary
    # the harness spawns this interpreter, so the version and the platform are this process's
    assert environment["python"] == platform.python_version()
    assert environment["platform"] == platform.platform()
    cvc5 = environment["cvc5"]
    assert isinstance(cvc5, str) and cvc5, summary


def totals_of(summary: dict[str, object]) -> dict[str, int]:
    """How many lines each file has, off the summary line."""
    payload = summary["total"]
    assert isinstance(payload, dict), summary
    return {str(file): int(count) for file, count in payload.items()}


def after_the_last_trace(stderr: str) -> list[str]:
    """The stderr lines that sum the run, past the last input's own trace.

    Every input's trace ends on its ``downgrades`` line, so the last one is
    where the run's summary starts.
    """
    lines = stderr.splitlines()
    last = max(at for at, line in enumerate(lines) if line.startswith("downgrades "))
    return lines[last + 1 :]


# finish-a-run-writes-the-summary-to-stderr
def test_writes_the_summary_to_stderr() -> None:
    result = run_pyct(ONE_CHECK, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    summary = summary_line(result.stdout)
    covered = numbers_of(summary, "covered")
    total = totals_of(summary)
    (file,) = covered
    summed = after_the_last_trace(result.stderr)
    # the words are the per-input trace's, over the run's own counts
    assert summed[0] == f"covered {len(covered[file])} of {total[file]} lines in {file}"
    assert summed[1] == "solver: 1 sat, 0 unsat, 0 unknown, 0 timeout"
    assert summed[-1].startswith("stopped: "), result.stderr


# finish-a-run-lists-uncovered-lines
def test_lists_uncovered_lines() -> None:
    result = run_pyct(UNFOLLOWED_GUARD, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    summary = summary_line(result.stdout)
    uncovered = numbers_of(summary, "uncovered")
    assert NEVER in uncovered[UNFOLLOWED_GUARD_FILE], summary
    named = [line for line in after_the_last_trace(result.stderr) if line.startswith("uncovered ")]
    assert len(named) == 1, result.stderr
    numbers = named[0].removeprefix("uncovered ").removesuffix(f" in {UNFOLLOWED_GUARD_FILE}")
    assert str(NEVER) in numbers.split(", "), result.stderr


# finish-a-run-prints-the-summary-after-the-seed-alone
def test_prints_the_summary_after_the_seed_alone() -> None:
    result = run_pyct(NO_CHECK, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    # the seed's line and the summary, and nothing else: no fork means no second input
    assert len(result.stdout.splitlines()) == 2, result.stdout
    (seed,) = input_lines(result.stdout)
    assert seed["source"] == "seed"
    summary = summary_line(result.stdout)
    assert summary["stopped"] == "no fork to flip"
    assert summary["inputs"] == 1
    # the solver was never asked, so every kind of answer is at zero
    assert summary["solver"] == ZERO_ANSWERS
    assert summary["misses"] == []


# finish-a-run-prints-the-summary-when-the-solver-crashes
def test_prints_the_summary_when_the_solver_crashes(tmp_path: Path) -> None:
    script = crashing_cvc5(tmp_path)

    result = run_pyct(ONE_CHECK, '{"x": 3}', path=str(tmp_path))

    assert result.returncode == 1, result.stderr
    # the crash ends the run, and the summary still closes stdout behind the seed's line
    assert len(result.stdout.splitlines()) == 2, result.stdout
    (seed,) = input_lines(result.stdout)
    assert seed["source"] == "seed"
    summary = summary_line(result.stdout)
    assert summary["stopped"] == "solver failed"
    assert summary["inputs"] == 1
    # the one call ended in a crash, which is no answer of any kind
    assert summary["solver"] == ZERO_ANSWERS
    environment = summary["environment"]
    assert isinstance(environment, dict), summary
    # the same cvc5 fails --version, and a failed probe is a null rather than a stop
    assert environment["cvc5"] is None, summary
    # the probe runs before the seed, so its warning lands above the trace, not inside it
    stderr = result.stderr.splitlines()
    assert stderr[0] == f"{script} --version exited 1", result.stderr
    assert stderr[1] == 'seed {"x": 3}', result.stderr
