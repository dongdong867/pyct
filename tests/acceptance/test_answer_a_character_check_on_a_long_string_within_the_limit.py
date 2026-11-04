"""Acceptance tests for answer-a-character-check-on-a-long-string-within-the-limit: the checks a
loop makes on each character of a string are answered within the solver's limit, and keep
their answers.

Each test spawns ``python -P -m pyct`` through the harness, so the asks are the ones a run
writes.
"""

from tests.acceptance.harness import REPO_ROOT, run_pyct, summary_line

UPPER_AND_DIGIT = "targets.strs.upper_and_digit::both"
UPPER_AND_DIGIT_FILE = str(REPO_ROOT / "targets" / "strs" / "upper_and_digit.py")


# answer-a-character-check-on-a-long-string-within-the-limit-keeps-a-contradiction-unsat
def test_an_uppercase_digit_stays_unsat() -> None:
    # the loop lengthens the string with each pass, so only a budget ends the run
    result = run_pyct(UPPER_AND_DIGIT, '{"s": "aB1"}', "--budget", "5", timeout=60)

    assert result.returncode == 0, result.stderr
    summary = summary_line(result.stdout)
    assert summary["uncovered"] == {UPPER_AND_DIGIT_FILE: [4]}, summary
    # each flip into `return 1` makes `c.isdigit()` true on an uppercase character
    explained = summary["why_uncovered"]
    assert isinstance(explained, list) and len(explained) == 1, explained
    why = explained[0]
    condition = {"file": UPPER_AND_DIGIT_FILE, "line": 3, "col": 27, "side": True}
    assert why["condition"] == condition, why
    tries = why["tries"]
    assert tries["unsat"] > 0, why
    assert [tries[kind] for kind in ("unknown", "timeout", "left_the_plan", "decided")] == [0] * 4
    misses = summary["misses"]
    assert isinstance(misses, list)
    assert {miss["why"] for miss in misses if miss["line"] == 3 and miss["col"] == 27} == {"unsat"}
