"""Acceptance tests for the follow-integers story.

Each test spawns ``python -P -m pyct`` through the harness, the way the finish-a-run
tests do: an operation is followed only if the fork it built reaches the solver and the
solver's answer runs, so only a real run through the command line proves it.
"""

from tests.acceptance.harness import REPO_ROOT, input_lines, run_pyct, summary_line, two_lines

SIX_CHECKS = "targets.ints.six_checks::count"
SIX_CHECKS_FILE = str(REPO_ROOT / "targets" / "ints" / "six_checks.py")
# every line of ``count`` but its ``def``, which runs at import rather than under an input
COUNT_LINES = list(range(2, 16))
REFLECTED_CHECK = "targets.ints.reflected_check::rank"
REFLECTED_CHECK_FILE = str(REPO_ROOT / "targets" / "ints" / "reflected_check.py")


def argument(line: dict[str, object], name: str) -> int:
    """One int argument off a printed line, narrowed so the comparison means something."""
    args = line["args"]
    assert isinstance(args, dict), line
    value = args[name]
    assert isinstance(value, int), line
    return value


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


# follow-integers-flips-a-reflected-comparison
def test_flips_a_reflected_comparison() -> None:
    result = run_pyct(REFLECTED_CHECK, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    # Python swaps the operands of `10 < x` itself, so the fork is the one it ran, `x > 10`
    assert seed["forks"] == [
        {
            "file": REFLECTED_CHECK_FILE,
            "line": 2,
            "col": 7,
            "taken": False,
            "expression": [">", "x", 10],
        }
    ]
    assert solved["forks"] == [
        {
            "file": REFLECTED_CHECK_FILE,
            "line": 2,
            "col": 7,
            "taken": True,
            "expression": [">", "x", 10],
        }
    ]
    assert argument(solved, "x") > 10
