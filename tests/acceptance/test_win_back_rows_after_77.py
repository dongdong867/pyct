"""Acceptance tests for the win-back-three-rows-the-full-run-lost-after-77 bug.

Each test spawns ``python -P -m pyct`` through the harness with the real cvc5. The first holds
the card number's cause: `int(ch)` for each character of a long string, which cvc5 read through
the whole grammar and answered past its limit. The second holds the version's cause: `int(s)`
after `s.isdigit()` in a helper, whose flip only a string of more digits than Python reads takes,
so each call's fork ran to the solver's limit before any other.
"""

from tests.acceptance.harness import REPO_ROOT, input_lines, run_pyct, summary_line

DIGIT_CHECKSUM = "targets.strs.digit_checksum::checksum"
DIGIT_CHECKSUM_FILE = str(REPO_ROOT / "targets" / "strs" / "digit_checksum.py")
# each ``return``, and the digit doubled past 9
DIGIT_CHECKSUM_LINES = {3, 10, 13, 14}
DIGIT_FIELDS = "targets.flip.digit_fields::fields"
DIGIT_FIELDS_FILE = str(REPO_ROOT / "targets" / "flip" / "digit_fields.py")
# ``int(text)``, where each call reads its field
READ_AS_INT = f"{DIGIT_FIELDS_FILE}:3:15"


def covered_in(stdout: str, file: str) -> set[int]:
    """The lines of one file any input ran."""
    lines: set[int] = set()
    for line in input_lines(stdout):
        covered = line["covered"]
        assert isinstance(covered, dict), line
        lines |= {int(number) for number in covered.get(file, [])}
    return lines


def test_flips_every_fork_of_a_loop_that_reads_each_character_as_an_int() -> None:
    result = run_pyct(DIGIT_CHECKSUM, '{"number": "41111111"}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    assert covered_in(result.stdout, DIGIT_CHECKSUM_FILE) >= DIGIT_CHECKSUM_LINES, result.stdout
    solver = summary_line(result.stdout)["solver"]
    assert isinstance(solver, dict) and solver["timeout"] == 0, result.stdout


def test_a_timeout_sends_the_other_forks_at_its_site_last() -> None:
    seed = '{"a": "1", "b": "2", "c": "3"}'

    result = run_pyct(DIGIT_FIELDS, seed, "--budget", "10", "--solver-timeout", "1")

    assert result.returncode == 0, result.stderr
    events = [
        line
        for line in result.stderr.splitlines()
        if line.startswith("aim ") or line.startswith("missed ")
    ]
    timeouts = [at for at, line in enumerate(events) if line == f"missed {READ_AS_INT} timeout"]
    # the seed's deepest fork, the third call's `int(text)`, runs to the limit first
    assert timeouts and timeouts[0] == 0, result.stderr
    # each field's `isdigit` flip, the last two by the oldest-path order, comes before the other
    # calls' `int(text)`, which wait for the last picks
    aims = [at for at, line in enumerate(events) if line.startswith("aim ")]
    assert len(aims) == 3 and len(timeouts) == 3, result.stderr
    assert max(aims) < timeouts[1], result.stderr
    assert covered_in(result.stdout, DIGIT_FIELDS_FILE) >= {8, 10, 12}, result.stdout
