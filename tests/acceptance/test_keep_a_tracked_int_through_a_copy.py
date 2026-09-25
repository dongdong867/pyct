"""Acceptance tests for the keep-a-tracked-int-through-a-copy bug.

Each test spawns ``python -P -m pyct`` through the harness, the way the follow-integers
tests do: a copy keeps the int tracked only if the fork after it reaches the solver and
the solver's answer runs, so only a real run through the command line proves it.
"""

from tests.acceptance.harness import REPO_ROOT, input_lines, run_pyct, summary_line, two_lines

DEEP_COPY = "targets.ints.deep_copy::check"
DEEP_COPY_FILE = str(REPO_ROOT / "targets" / "ints" / "deep_copy.py")
COMPARE_DEEP_COPY = "targets.ints.compare_deep_copy::check"
COMPARE_DEEP_COPY_FILE = str(REPO_ROOT / "targets" / "ints" / "compare_deep_copy.py")
EACH_COPY = "targets.ints.each_copy::count"
# the line of each fork in ``count``: three on a copied int, then three on a copied compare
EACH_COPY_LINES = [12, 14, 16, 18, 20, 22]


def argument(line: dict[str, object], name: str) -> int:
    """One int argument off a printed line, narrowed so the comparison means something."""
    args = line["args"]
    assert isinstance(args, dict), line
    value = args[name]
    assert isinstance(value, int), line
    return value


def forks_of(line: dict[str, object]) -> list[dict[str, object]]:
    """The forks off a printed line, narrowed so a field lookup means something."""
    forks = line["forks"]
    assert isinstance(forks, list), line
    return [dict(fork) for fork in forks]


# keep-a-tracked-int-through-a-copy-flips-an-int-after-a-deep-copy
def test_flips_an_int_after_a_deep_copy() -> None:
    result = run_pyct(DEEP_COPY, '{"n": 3}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    # the copy is the tracked int itself, so the compare after it is the fork
    fork = {"file": DEEP_COPY_FILE, "line": 6, "col": 7, "expression": [">", "n", 10]}
    assert seed["failure"] is None
    assert forks_of(seed) == [{**fork, "taken": False}]
    assert forks_of(solved) == [{**fork, "taken": True}]
    assert argument(solved, "n") > 10


# keep-a-tracked-int-through-a-copy-flips-a-compare-result-after-a-deep-copy
def test_flips_a_compare_result_after_a_deep_copy() -> None:
    result = run_pyct(COMPARE_DEEP_COPY, '{"n": 3}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    # the compare ran before the copy, and the truth test after it records its condition
    fork = {"file": COMPARE_DEEP_COPY_FILE, "line": 6, "col": 7, "expression": [">", "n", 10]}
    assert seed["failure"] is None
    assert forks_of(seed) == [{**fork, "taken": False}]
    assert forks_of(solved) == [{**fork, "taken": True}]
    assert argument(solved, "n") > 10


# keep-a-tracked-int-through-a-copy-keeps-it-through-each-copy
def test_keeps_it_through_each_copy() -> None:
    result = run_pyct(EACH_COPY, '{"n": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # every fork is flipped: some input takes each side of each copy's fork
    sides = {(fork["line"], fork["taken"]) for line in inputs for fork in forks_of(line)}
    assert sides == {(line, taken) for line in EACH_COPY_LINES for taken in (True, False)}
    assert [line["failure"] for line in inputs] == [None] * len(inputs)
    # a copy is the value itself, so no input loses a condition to it
    assert [line["downgrades"] for line in inputs] == [[]] * len(inputs)
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"
