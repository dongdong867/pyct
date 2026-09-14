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
IMPLIED_CHECK = "targets.flip.implied_check::narrow"
IMPLIED_CHECK_FILE = str(REPO_ROOT / "targets" / "flip" / "implied_check.py")
# ``if x < 10:``, which cannot go the other way while the ``x < 5`` above it holds
IMPLIED = 3
RAISES_BEHIND_A_SECOND_FORK = "targets.flip.raises_behind_a_second_fork::guard"
TWO_CHECKS = "targets.trace.two_checks::bucket"
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


def aim_of(line: dict[str, object]) -> tuple[str, int, int, int] | None:
    """The fork one input aimed at, as a value two lines can be compared by.

    ``None`` on the seed's line, which aimed at nothing.
    """
    aim = line["aim"]
    if aim is None:
        return None
    assert isinstance(aim, dict), line
    return str(aim["file"]), int(aim["line"]), int(aim["col"]), int(aim["position"])


# finish-a-run-aims-each-fork-once
def test_aims_each_fork_once() -> None:
    result = run_pyct(NESTED_CHECKS, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    solver = [line for line in lines if line["source"] == "solver"]
    # one solver input per way out the seed left open, each after a fork of its own
    assert len(solver) == 2, result.stdout
    assert aim_of(solver[0]) != aim_of(solver[1]), result.stdout
    # a fork is spent the moment it is aimed at, so no aim comes back on a later line
    aimed = [aim for aim in (aim_of(line) for line in lines) if aim is not None]
    assert len(set(aimed)) == len(aimed), result.stdout


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


# finish-a-run-counts-solver-answers
def test_counts_solver_answers() -> None:
    result = run_pyct(IMPLIED_CHECK, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    summary = summary_line(result.stdout)
    # the outer check flipped; the inner one the outer implies could not
    assert summary["solver"] == {"sat": 1, "unsat": 1, "unknown": 0, "timeout": 0}
    misses = summary["misses"]
    assert isinstance(misses, list) and len(misses) == 1, summary
    (miss,) = misses
    assert isinstance(miss, dict), summary
    assert miss["file"] == IMPLIED_CHECK_FILE, summary
    assert miss["line"] == IMPLIED, summary
    assert miss["why"] == "unsat", summary


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


def failure_kind(line: dict[str, object]) -> str | None:
    """How one input failed, off its printed line. ``None`` when it ran to the end."""
    failure = line["failure"]
    if failure is None:
        return None
    assert isinstance(failure, dict), line
    return str(failure["kind"])


# finish-a-run-keeps-going-after-a-failed-input
def test_keeps_going_after_a_failed_input() -> None:
    result = run_pyct(RAISES_BEHIND_A_SECOND_FORK, '{"x": 50}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    raised = [at for at, line in enumerate(lines) if failure_kind(line) == "target_raised"]
    assert raised, result.stdout
    # the fork the raising input hit is still open, so the loop runs an input for it
    assert raised[0] < len(lines) - 1, result.stdout


# finish-a-run-runs-without-a-plateau
def test_runs_without_a_plateau() -> None:
    result = run_pyct(TWO_CHECKS, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    # the second check is implied by the first: the seed, then the two flips cvc5 can
    # make; the try at the implied check is unsat and prints no line
    assert len(input_lines(result.stdout)) == 3, result.stdout
    # nothing stops the loop early, because no plateau was asked for
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# finish-a-run-refuses-a-bad-plateau
def test_refuses_a_bad_plateau() -> None:
    for bad in ["0", "-1", "2.5", "abc"]:
        result = run_pyct(ONE_CHECK, '{"x": 3}', "--plateau", bad)

        assert result.returncode == 2, bad
        assert result.stdout == "", bad
        assert "plateau must be a whole number above zero" in result.stderr, bad


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
