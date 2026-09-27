"""Acceptance tests for the make-a-downgraded-result-plain bug.

Each test spawns ``python -P -m pyct`` through the harness: the bug was a fork recorded on
the result of a downgrade, and only a real run shows which forks reach the line and which
input the solver hands back.
"""

from tests.acceptance.harness import (
    REPO_ROOT,
    downgrade,
    first_line,
    one_line,
    run_pyct,
    second_line,
)
from tests.acceptance.test_strs import forks_of, text

MOD_EMPTY = "targets.strs.nothing_to_fill::mod_empty"
FORMAT_EMPTY = "targets.strs.nothing_to_fill::format_empty"
MOD_THEN_ITSELF = "targets.strs.nothing_to_fill::mod_then_itself"
NOTHING_TO_FILL_FILE = str(REPO_ROOT / "targets" / "strs" / "nothing_to_fill.py")


# make-a-downgraded-result-plain-drops-the-fork-after-mod
def test_drops_the_fork_after_mod() -> None:
    result = run_pyct(MOD_EMPTY, '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    # str's `%` hands back s itself when there is nothing to fill in, and the target gets it
    # plain, so the compare after it is Python's own and the run has nothing to flip
    seed = one_line(result.stdout)
    assert seed["failure"] is None
    assert seed["downgrades"] == [downgrade("__mod__", 1, "targets/strs/nothing_to_fill.py:2:8")]
    assert seed["forks"] == []


# make-a-downgraded-result-plain-drops-the-fork-after-format
def test_drops_the_fork_after_format() -> None:
    result = run_pyct(FORMAT_EMPTY, '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    assert seed["failure"] is None
    assert seed["downgrades"] == [downgrade("format", 1, "targets/strs/nothing_to_fill.py:9:8")]
    assert seed["forks"] == []


# make-a-downgraded-result-plain-keeps-the-str-itself-tracked
def test_keeps_the_str_itself_tracked() -> None:
    result = run_pyct(MOD_THEN_ITSELF, '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    seed, solved = first_line(result.stdout), second_line(result.stdout)
    # the result is plain, and s, which the downgrade read, keeps its condition
    fork = {"file": NOTHING_TO_FILL_FILE, "line": 17, "col": 7, "expression": ["==", "s", "'abc'"]}
    assert seed["downgrades"] == [downgrade("__mod__", 1, "targets/strs/nothing_to_fill.py:16:8")]
    assert forks_of(seed) == [{**fork, "taken": False}]
    assert text(solved, "s") == "abc"
    assert forks_of(solved) == [{**fork, "taken": True}]
