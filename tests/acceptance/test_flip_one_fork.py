"""Acceptance tests for the flip-one-fork story, child run-the-second-input-and-print-its-line.

Each test spawns ``python -P -m pyct`` through the harness, the way the trace-the-seed
tests do: the second input is the solver's, so only a real run through the command line
proves pyct found cvc5, flipped the fork, and printed the line.
"""

from pathlib import Path

from tests.acceptance.harness import (
    CRASH_DETAIL,
    REPO_ROOT,
    crashing_cvc5,
    first_line,
    one_line,
    run_pyct,
    second_line,
    two_lines,
)

ONE_CHECK = "targets.flip.one_check::classify"
ONE_CHECK_FILE = str(REPO_ROOT / "targets" / "flip" / "one_check.py")
NESTED_CHECKS = "targets.flip.nested_checks::bucket"
NESTED_CHECKS_FILE = str(REPO_ROOT / "targets" / "flip" / "nested_checks.py")
TWO_ARGS = "targets.flip.two_args::pick"
OTHER_SIDE_LONGER = "targets.flip.other_side_longer::grade"
OTHER_SIDE_LONGER_FILE = str(REPO_ROOT / "targets" / "flip" / "other_side_longer.py")
NO_CHECK = "targets.flip.no_check::echo"
SPINS_AFTER_A_CHECK = "targets.flip.spins_after_a_check::spin"
IMPLIED_CHECK = "targets.flip.implied_check::narrow"
IMPLIED_CHECK_FILE = str(REPO_ROOT / "targets" / "flip" / "implied_check.py")
RAISES_AFTER_A_CHECK = "targets.flip.raises_after_a_check::probe"
RAISES_AFTER_A_CHECK_FILE = str(REPO_ROOT / "targets" / "flip" / "raises_after_a_check.py")
RAISES_ON_THE_OTHER_SIDE = "targets.flip.raises_on_the_other_side::guard"
UNTAUGHT_GUARD = "targets.flip.untaught_guard::route"
UNTAUGHT_GUARD_FILE = str(REPO_ROOT / "targets" / "flip" / "untaught_guard.py")
CUT_SHORT_ON_THE_OTHER_SIDE = "targets.flip.cut_short_on_the_other_side::cut"
CUT_SHORT_ON_THE_OTHER_SIDE_FILE = str(
    REPO_ROOT / "targets" / "flip" / "cut_short_on_the_other_side.py"
)


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
    solved = second_line(result.stdout)
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


# flip-one-fork-stops-when-the-seed-spent-the-budget
def test_stops_when_the_seed_spent_the_budget() -> None:
    result = run_pyct(SPINS_AFTER_A_CHECK, '{"x": 3}', "--budget", "1")

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    failure = seed["failure"]
    assert isinstance(failure, dict)
    assert failure["kind"] == "timeout"
    # the seed hit a fork, so only the spent budget kept the solver from being asked
    forks = seed["forks"]
    assert isinstance(forks, list) and len(forks) == 1, seed
    assert result.stderr.splitlines()[-1] == "stopped: budget spent"


# flip-one-fork-reports-unsat
def test_reports_unsat() -> None:
    result = run_pyct(IMPLIED_CHECK, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert seed["source"] == "seed"
    # the inner check cannot go the other way while the outer one holds
    lines = result.stderr.splitlines()
    missed = f"missed {IMPLIED_CHECK_FILE}:3:11 unsat"
    assert missed in lines, result.stderr
    # an answer that gave no input is not why the run ended; it ran out of forks
    assert lines[-1] == "stopped: no fork to flip"
    # the miss prints the moment the solver answers, so it lands before the next input's trace
    solved = [at for at, line in enumerate(lines) if line.startswith("solver ")]
    assert solved, result.stderr
    assert lines.index(missed) < solved[0], result.stderr


# flip-one-fork-fails-when-the-solver-crashes
def test_fails_when_the_solver_crashes(tmp_path: Path) -> None:
    crashing_cvc5(tmp_path)

    result = run_pyct(ONE_CHECK, '{"x": 3}', path=str(tmp_path))

    assert result.returncode == 1, result.stderr
    seed = one_line(result.stdout)
    assert seed["source"] == "seed"
    lines = result.stderr.splitlines()
    assert lines[-2:] == [
        "stopped: solver failed",
        f"    {CRASH_DETAIL}",
    ]


# flip-one-fork-flips-after-the-seed-raised
def test_flips_after_the_seed_raised() -> None:
    result = run_pyct(RAISES_AFTER_A_CHECK, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    assert seed["failure"] == {"kind": "target_raised", "detail": "ValueError: too small"}
    # a raise is an end, not a stop: the fork the seed reached is still flipped
    assert solved["source"] == "solver"
    assert solved["aim"] == {
        "file": RAISES_AFTER_A_CHECK_FILE,
        "line": 2,
        "col": 7,
        "position": 0,
    }


# flip-one-fork-reports-the-second-input-failure
def test_reports_the_second_input_failure() -> None:
    result = run_pyct(RAISES_ON_THE_OTHER_SIDE, '{"x": 3}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    assert seed["failure"] is None
    # the raise waits on the side the seed missed, so the second line is the one that carries it
    assert solved["failure"] == {"kind": "target_raised", "detail": "ValueError: out of range"}


# flip-one-fork-reports-going-off-course
def test_reports_going_off_course() -> None:
    result = run_pyct(UNTAUGHT_GUARD, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    solved = second_line(result.stdout)
    # ``>>`` is an operation pyct has not taught, and the int it returns is tested for
    # truth, so the seed records only ``x < 10``, at position 0
    assert solved["aim"] == {"file": UNTAUGHT_GUARD_FILE, "line": 6, "col": 7, "position": 0}
    # the flip asks for x >= 10, and every such x shifts to something above zero, so every
    # model cvc5 can return enters the block and hits ``x < 20`` at position 0 instead; the
    # guard holds for the whole side being asked for, so the test does not depend on the
    # model picked
    assert solved["mismatch_at"] == 0
    forks = solved["forks"]
    assert isinstance(forks, list) and forks, solved
    assert forks[0] == {
        "file": UNTAUGHT_GUARD_FILE,
        "line": 3,
        "col": 11,
        "taken": argument(solved, "x") < 20,
        "expression": ["<", "x", 20],
    }
    # the trace names the fork that was hit, not only the position it happened at
    assert f"left the plan at position 0, hit {UNTAUGHT_GUARD_FILE}:3:11" in result.stderr


# .ddlc/features/run/README.md › Rules › the stderr trace: ``no fork there``
def test_reports_going_off_course_where_the_run_stopped_forking() -> None:
    result = run_pyct(CUT_SHORT_ON_THE_OTHER_SIDE, '{"x": 1}')

    assert result.returncode == 0, result.stderr
    solved = second_line(result.stdout)
    # the seed takes ``x < 6`` then ``x < 5``; flipping the second under the first admits
    # only x == 5, which divides by zero before the second fork is tested
    assert solved["aim"] == {
        "file": CUT_SHORT_ON_THE_OTHER_SIDE_FILE,
        "line": 4,
        "col": 11,
        "position": 1,
    }
    # the detail is CPython's own sentence, and 3.14 shortened it, so only the kind
    # and the exception's name are pyct's to pin
    failure = solved["failure"]
    assert isinstance(failure, dict), solved
    assert failure["kind"] == "target_raised"
    assert str(failure["detail"]).startswith("ZeroDivisionError:")
    # the plan had two forks and the run recorded one, so the mismatch sits past the path
    assert solved["forks"] == [
        {
            "file": CUT_SHORT_ON_THE_OTHER_SIDE_FILE,
            "line": 2,
            "col": 7,
            "taken": True,
            "expression": ["<", "x", 6],
        }
    ]
    assert solved["mismatch_at"] == 1
    # the trace says there was nothing at that position rather than naming a fork
    assert "left the plan at position 1, no fork there" in result.stderr
