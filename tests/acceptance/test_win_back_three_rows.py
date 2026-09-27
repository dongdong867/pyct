"""Acceptance tests for the win-back-three-rows-the-full-run-lost-after-69 bug.

Each test spawns ``python -P -m pyct`` through the harness with the real cvc5. The first
holds the card-number rows' cause: a check on a string the path holds long, which cvc5
answered only past its limit while the check was written as counts. The second holds the
url row's cause: a seed whose deepest forks cvc5 cannot answer, which spent the budget on
them one after another.
"""

from tests.acceptance.harness import REPO_ROOT, input_lines, run_pyct, summary_line

LONG_DIGITS = "targets.strs.long_digits::card"
LONG_DIGITS_FILE = str(REPO_ROOT / "targets" / "strs" / "long_digits.py")
# each ``return``, one per side the seed's forks lead to
LONG_DIGITS_RETURNS = {4, 6, 8, 9}
HARD_FORKS_LAST = "targets.flip.hard_forks_last::triage"
HARD_FORKS_LAST_FILE = str(REPO_ROOT / "targets" / "flip" / "hard_forks_last.py")
# ``sign = "not positive"``, which only an input with n <= 0 runs
NOT_POSITIVE = 4


def covered_in(stdout: str, file: str) -> set[int]:
    """The lines of one file any input ran."""
    lines: set[int] = set()
    for line in input_lines(stdout):
        covered = line["covered"]
        assert isinstance(covered, dict), line
        lines |= {int(number) for number in covered.get(file, [])}
    return lines


def solver_counts(stdout: str) -> dict[str, object]:
    solver = summary_line(stdout)["solver"]
    assert isinstance(solver, dict), stdout
    return solver


def test_flips_every_fork_of_a_long_string_one_check_reads() -> None:
    result = run_pyct(LONG_DIGITS, '{"number": "4111111111111111"}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    assert covered_in(result.stdout, LONG_DIGITS_FILE) >= LONG_DIGITS_RETURNS, result.stdout
    assert solver_counts(result.stdout)["timeout"] == 0, result.stdout
    assert summary_line(result.stdout)["stopped"] == "no fork to flip", result.stdout


def test_a_timeout_sends_the_next_input_to_the_seed_s_first_fork() -> None:
    seed = '{"n": 1, "s": "a", "t": "b", "u": "c"}'

    result = run_pyct(HARD_FORKS_LAST, seed, "--budget", "3", "--solver-timeout", "1")

    assert result.returncode == 0, result.stderr
    # the order below rests on the seed's deepest fork running to the solver's limit
    timeouts = solver_counts(result.stdout)["timeout"]
    assert isinstance(timeouts, int) and timeouts >= 1, result.stdout
    solved = [line for line in input_lines(result.stdout) if line["source"] == "solver"]
    # the seed's deepest fork timed out, so the next pick is the seed's first fork, n <= 0
    assert solved, result.stdout
    assert solved[0]["aim"] == {"file": HARD_FORKS_LAST_FILE, "line": 3, "col": 7, "position": 0}
    assert NOT_POSITIVE in covered_in(result.stdout, HARD_FORKS_LAST_FILE), result.stdout
