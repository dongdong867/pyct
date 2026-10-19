"""Acceptance tests for the `count` part of close-four-small-v1-gaps: a count of a separator
beside the pieces a split on it makes is answered within the solver's limit.

Each test spawns ``python -P -m pyct`` through the harness, so the asks are the ones a run
writes.
"""

import inspect

from targets.strs import count_beside_split
from tests.acceptance.harness import REPO_ROOT, run_pyct, summary_line

COUNTED = "targets.strs.count_beside_split"
COUNTED_FILE = str(REPO_ROOT / "targets" / "strs" / "count_beside_split.py")


def uncovered_in(stdout: str, function: object) -> list[int]:
    """The lines of one function of the fixture the run left uncovered."""
    lines, first = inspect.getsourcelines(function)  # pyrefly: ignore[bad-argument-type]
    uncovered = summary_line(stdout)["uncovered"]
    assert isinstance(uncovered, dict), stdout
    return [line for line in uncovered[COUNTED_FILE] if first <= line < first + len(lines)]


# close-four-small-v1-gaps-count-answers-beside-split-pieces
def test_answers_beside_split_pieces() -> None:
    result = run_pyct(f"{COUNTED}::address", '{"email": ""}', "--budget", "30", timeout=60)

    assert result.returncode == 0, result.stderr
    # every line, the one only a long second piece reaches among them, and no ask ran out
    assert uncovered_in(result.stdout, count_beside_split.address) == []
    seconds = summary_line(result.stdout)["solver_seconds"]
    assert isinstance(seconds, dict) and seconds["timeout"] == 0 and seconds["unknown"] == 0


def test_reaches_a_long_piece_beside_a_count_of_two() -> None:
    result = run_pyct(f"{COUNTED}::fields", '{"line": ""}', "--budget", "30", timeout=60)

    assert result.returncode == 0, result.stderr
    assert uncovered_in(result.stdout, count_beside_split.fields) == []
