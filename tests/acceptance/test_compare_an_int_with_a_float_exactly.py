"""Acceptance tests for compare-an-int-with-a-float-exactly: an int meets a float in a compare
exactly, as Python compares them, so an int no double holds takes the side Python gives it.

Each test spawns ``python -P -m pyct`` through the harness, so the asks are the ones a run
writes.
"""

from tests.acceptance.harness import REPO_ROOT, argument, input_lines, numbers_of, run_pyct

FLOATS = REPO_ROOT / "targets" / "floats"


def covering(stdout: str, name: str, file: str, line: int) -> list[int]:
    """The int argument ``name`` of each input that covered the line of the file."""
    inputs = input_lines(stdout)
    return [argument(entry, name) for entry in inputs if line in numbers_of(entry, "covered")[file]]


# compare-an-int-with-a-float-exactly-covers-large-int
def test_covers_the_line_only_an_int_equal_to_a_large_double_reaches() -> None:
    result = run_pyct("targets.floats.large_int::near", '{"n": 0}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    # 9007199254740995 rounds to the double 9007199254740996.0 but is not equal to it in Python
    assert covering(result.stdout, "n", str(FLOATS / "large_int.py"), 3) == [9007199254740996]


# compare-an-int-with-a-float-exactly-flips-past-rounding
def test_reaches_the_only_int_between_two_doubles_which_rounding_cannot_reach() -> None:
    result = run_pyct("targets.floats.past_rounding::between", '{"x": 0}')

    assert result.returncode == 0, result.stderr
    # 2**53 + 1 is the only int between 2.0**53 and the next double, and rounds to one of them
    assert covering(result.stdout, "x", str(FLOATS / "past_rounding.py"), 3) == [2**53 + 1]
