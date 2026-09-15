"""Acceptance tests for the follow-integers story.

Each test spawns ``python -P -m pyct`` through the harness, the way the finish-a-run
tests do: an operation is followed only if the fork it built reaches the solver and the
solver's answer runs, so only a real run through the command line proves it.
"""

from tests.acceptance.harness import REPO_ROOT, input_lines, run_pyct, summary_line

SIX_CHECKS = "targets.ints.six_checks::count"
SIX_CHECKS_FILE = str(REPO_ROOT / "targets" / "ints" / "six_checks.py")
# every line of ``count`` but its ``def``, which runs at import rather than under an input
COUNT_LINES = list(range(2, 16))


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


# follow-integers-flips-every-comparison
def test_flips_every_comparison() -> None:
    result = run_pyct(SIX_CHECKS, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # the seed takes one side of each of the six checks; the other side of each is a fork
    # to flip, and the input that flips it runs the line under that check
    assert union_of(inputs) == {SIX_CHECKS_FILE: COUNT_LINES}
    summary = summary_line(result.stdout)
    # nothing is left over but the ``def`` line no input can run
    assert numbers_of(summary, "uncovered") == {SIX_CHECKS_FILE: [1]}
    assert summary["stopped"] == "no fork to flip"
