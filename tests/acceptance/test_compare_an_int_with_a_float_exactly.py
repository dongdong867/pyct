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
def test_flips_a_compare_an_int_takes_only_past_where_a_double_rounds_it() -> None:
    result = run_pyct("targets.floats.past_rounding::above", '{"x": 0}')

    assert result.returncode == 0, result.stderr
    # 2**53 + 1 rounds to the double 2.0**53, but Python compares it exactly and it is above
    assert covering(result.stdout, "x", str(FLOATS / "past_rounding.py"), 3) == [2**53 + 1]
