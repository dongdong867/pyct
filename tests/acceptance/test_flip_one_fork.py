"""Acceptance tests for the flip-one-fork story, child run-the-second-input-and-print-its-line.

Each test spawns ``python -P -m pyct`` through the harness, the way the trace-the-seed
tests do: the second input is the solver's, so only a real run through the command line
proves pyct found cvc5, flipped the fork, and printed the line.
"""

from pathlib import Path

from tests.acceptance.harness import REPO_ROOT, one_line, run_pyct, two_lines

ONE_CHECK = "targets.flip.one_check::classify"
ONE_CHECK_FILE = str(REPO_ROOT / "targets" / "flip" / "one_check.py")
NESTED_CHECKS = "targets.flip.nested_checks::bucket"
NESTED_CHECKS_FILE = str(REPO_ROOT / "targets" / "flip" / "nested_checks.py")
TWO_ARGS = "targets.flip.two_args::pick"
OTHER_SIDE_LONGER = "targets.flip.other_side_longer::grade"
OTHER_SIDE_LONGER_FILE = str(REPO_ROOT / "targets" / "flip" / "other_side_longer.py")
NO_CHECK = "targets.flip.no_check::echo"


def argument(line: dict[str, object], name: str) -> int:
    """One int argument off a printed line, narrowed so the comparison means something."""
    args = line["args"]
    assert isinstance(args, dict), line
    value = args[name]
    assert isinstance(value, int), line
    return value


# flip-one-fork-refuses-without-cvc5
def test_refuses_without_cvc5(tmp_path: Path) -> None:
    empty = str(tmp_path)

    result = run_pyct(ONE_CHECK, '{"x": 3}', path=empty)

    assert result.returncode == 1, result.stderr
    assert result.stdout == ""
    assert "cvc5" in result.stderr
    assert "not found" in result.stderr
    assert empty in result.stderr
    assert "install" in result.stderr


# flip-one-fork-prints-a-second-line
def test_prints_a_second_line() -> None:
    result = run_pyct(ONE_CHECK, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    assert seed["source"] == "seed"
    assert seed["aim"] is None
    assert seed["mismatch_at"] is None
    assert solved["source"] == "solver"
    # the one fork the seed hit, aimed at and taken the other way
    assert solved["aim"] == {"file": ONE_CHECK_FILE, "line": 2, "col": 7, "position": 0}
    assert solved["mismatch_at"] is None
    assert solved["forks"] == [
        {
            "file": ONE_CHECK_FILE,
            "line": 2,
            "col": 7,
            "taken": False,
            "expression": ["<", "x", 10],
        }
    ]
    assert argument(solved, "x") >= 10


# flip-one-fork-flips-the-last-fork
def test_flips_the_last_fork() -> None:
    result = run_pyct(NESTED_CHECKS, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    _, solved = two_lines(result.stdout)
    # the outer check keeps the side the seed took; only the last fork turns over
    assert solved["forks"] == [
        {
            "file": NESTED_CHECKS_FILE,
            "line": 2,
            "col": 7,
            "taken": True,
            "expression": ["<", "x", 100],
        },
        {
            "file": NESTED_CHECKS_FILE,
            "line": 3,
            "col": 11,
            "taken": False,
            "expression": ["<", "x", 10],
        },
    ]
    assert solved["aim"] == {"file": NESTED_CHECKS_FILE, "line": 3, "col": 11, "position": 1}
    assert 10 <= argument(solved, "x") < 100


# flip-one-fork-keeps-untouched-arguments
def test_keeps_untouched_arguments() -> None:
    result = run_pyct(TWO_ARGS, '{"x": 3, "y": 7}')

    assert result.returncode == 0, result.stderr
    _, solved = two_lines(result.stdout)
    # only x is in the fork, so only x moves; y is the seed's
    assert argument(solved, "x") >= 10
    assert argument(solved, "y") == 7


# flip-one-fork-reports-what-the-second-input-covered
def test_reports_what_the_second_input_covered() -> None:
    result = run_pyct(OTHER_SIDE_LONGER, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    # each line carries the lines its own input ran, not the lines run so far
    assert seed["covered"] == {OTHER_SIDE_LONGER_FILE: [2, 3]}
    assert solved["covered"] == {OTHER_SIDE_LONGER_FILE: [2, 4, 5, 6]}
    assert seed["total"] == {OTHER_SIDE_LONGER_FILE: 6}
    assert solved["total"] == {OTHER_SIDE_LONGER_FILE: 6}


# flip-one-fork-writes-the-aim-to-stderr
def test_writes_the_aim_to_stderr() -> None:
    result = run_pyct(ONE_CHECK, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    lines = result.stderr.splitlines()
    assert lines[0] == 'seed {"x": 3}'
    solver = [at for at, line in enumerate(lines) if line.startswith('solver {"x": ')]
    assert len(solver) == 1, result.stderr
    at = solver[0]
    # where the second input was sent, and whether it arrived
    assert lines[at + 1] == f"aim {ONE_CHECK_FILE}:2:7 at position 0"
    assert lines[at + 2] == "reached"
    assert f"fork {ONE_CHECK_FILE}:2:7  x < 10  not taken" in lines[at:]


# flip-one-fork-has-nothing-to-flip
def test_has_nothing_to_flip() -> None:
    result = run_pyct(NO_CHECK, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    assert seed["source"] == "seed"
    # the trace ends with why the run stopped, after the seed's own lines
    assert result.stderr.splitlines()[-1] == "stopped: no fork to flip"
