"""Acceptance tests for the solve-a-finite-floor-division-fast perf ticket.

The first four tests hold the finite fork a rounding records over a float `//`,
`int(x // 2)` in ``targets.strs.float_position::cut``: it flips within a second, the gate's
limits cover the line past it, the per-merge files list the target with nothing accepted for
it, and the other forks' answers stay finite. The rest hold what the float rules answered
before: a quotient past the 2**50 bound stays a miss, a floor no double has stays unsat, and
the solver's limit still ends the flip. Each run spawns ``python -P -m pyct`` through the
harness with the real cvc5. The checker's own row for the target is held in
``tests/compare_coverage/acceptance/test_float_position.py``.
"""

import json
import math
import statistics
import time

from tests.acceptance.harness import REPO_ROOT, input_lines, run_pyct, summary_line

FLOAT_POSITION = "targets.strs.float_position::cut"
FLOAT_POSITION_FILE = str(REPO_ROOT / "targets" / "strs" / "float_position.py")
SEED = '{"s": "abc", "x": 2.0}'
PAST_THE_BOUND = "targets.floats.floor_past_the_bound::past"
NO_DOUBLE_HAS = "targets.floats.floor_no_double_has::never"
COMPARE = REPO_ROOT / "tools" / "compare_coverage"

# the rounding's finite fork, and the forks of the index `int(x // 2)` makes, by column
FINITE_FORK = (2, 9)
INDEX_FORKS = (2, 7)
FINITE_FORK_LINE = "math.isfinite(x // 2)  not taken"
EVERY_FORK_SAT = "solver: 4 sat, 0 unsat, 0 unknown, 0 timeout"


def aimed_at(stdout: str, site: tuple[int, int]) -> list[dict[str, object]]:
    """The solver inputs aimed at one fork of float_position.py, by line and column."""
    lines = []
    for line in input_lines(stdout):
        aim = line["aim"]
        if isinstance(aim, dict) and (aim["file"], aim["line"], aim["col"]) == (
            FLOAT_POSITION_FILE,
            *site,
        ):
            lines.append(line)
    return lines


def x_of(line: dict[str, object]) -> float:
    args = line["args"]
    assert isinstance(args, dict), line
    x = args["x"]
    assert isinstance(x, float), line
    return x


def raised_by_python(x: float) -> str:
    """What plain Python raises for `int(x // 2)` on x, as pyct reports a raise."""
    try:
        int(x // 2)
    except (ValueError, OverflowError) as error:
        return f"{type(error).__name__}: {error}"
    raise AssertionError(f"int({x} // 2) raised nothing")


def stderr_blocks(stderr: str) -> list[list[str]]:
    """Stderr's lines, one block per input: the seed's, then each solver input's."""
    blocks: list[list[str]] = []
    for line in stderr.splitlines():
        if line.startswith(("seed {", "solver {")):
            blocks.append([])
        if blocks:
            blocks[-1].append(line)
    return blocks


def covered(stdout: str) -> list[int]:
    lines = summary_line(stdout)["covered"]
    assert isinstance(lines, dict), stdout
    return sorted(lines[FLOAT_POSITION_FILE])


def timed_run(*argv: str) -> tuple[float, str, str]:
    """One run of float_position from the seed, its wall time, its stdout and its stderr."""
    started = time.monotonic()
    result = run_pyct(FLOAT_POSITION, SEED, "--budget", "30", *argv, timeout=60)
    took = time.monotonic() - started
    assert result.returncode == 0, result.stderr
    return took, result.stdout, result.stderr


def flipped_to_a_raise(stdout: str, stderr: str) -> None:
    """The finite fork's flip handed back x NaN or infinite, whose input raised as Python does."""
    flips = aimed_at(stdout, FINITE_FORK)
    assert len(flips) == 1, stdout
    x = x_of(flips[0])
    assert not math.isfinite(x), flips[0]
    assert flips[0]["failure"] == {"kind": "target_raised", "detail": raised_by_python(x)}
    # the flip's stderr block is the one whose aim names the finite fork's column
    aim = f"aim {FLOAT_POSITION_FILE}:{FINITE_FORK[0]}:{FINITE_FORK[1]} "
    block = next(b for b in stderr_blocks(stderr) if any(line.startswith(aim) for line in b))
    assert any(line.endswith(FINITE_FORK_LINE) for line in block), block


# solve-a-finite-floor-division-fast-flips-the-finite-fork-within-a-second
def test_flips_the_finite_fork_within_a_second() -> None:
    for _ in range(3):
        _, stdout, stderr = timed_run("--solver-timeout", "1")
        flipped_to_a_raise(stdout, stderr)
        assert EVERY_FORK_SAT in stderr.splitlines(), stderr
        assert covered(stdout) == [2, 3, 4], stdout

    runs = [timed_run() for _ in range(3)]

    for _, stdout, stderr in runs:
        assert EVERY_FORK_SAT in stderr.splitlines(), stderr
        assert covered(stdout) == [2, 3, 4], stdout
    assert statistics.median(took for took, _, _ in runs) < 2.0


# solve-a-finite-floor-division-fast-covers-the-line-at-the-gate-limits
def test_covers_the_line_at_the_gate_limits() -> None:
    gate = ("--budget", "5", "--plateau", "5", "--solver-timeout", "10")

    result = run_pyct(FLOAT_POSITION, SEED, *gate)

    assert result.returncode == 0, result.stderr
    assert f"uncovered 1 in {FLOAT_POSITION_FILE}" in result.stderr.splitlines(), result.stderr
    assert "stopped: no fork to flip" in result.stderr.splitlines(), result.stderr


# solve-a-finite-floor-division-fast-puts-the-target-back-in-the-gate
def test_puts_the_target_back_in_the_gate() -> None:
    listed = json.loads((COMPARE / "targets.json").read_text())["entries"]
    accepted = [
        json.loads(line)
        for line in (COMPARE / "accepted-per-merge.jsonl").read_text().splitlines()[1:]
    ]

    entry = {"set": "v2", "target": FLOAT_POSITION, "seed": {"s": "abc", "x": 2.0}}
    assert entry in listed
    # a `same` row is accepted by nothing, so the file names the target no longer
    assert [row for row in accepted if row.get("target") == FLOAT_POSITION] == []


# solve-a-finite-floor-division-fast-keeps-other-answers-finite
def test_keeps_other_answers_finite() -> None:
    _, stdout, _ = timed_run()

    index_inputs = aimed_at(stdout, INDEX_FORKS)
    assert index_inputs, stdout
    assert all(math.isfinite(x_of(line)) for line in index_inputs), stdout
    # an input that reached its aim took every fork of its plan
    assert all(line["mismatch_at"] is None for line in index_inputs), stdout


# solve-a-finite-floor-division-fast-keeps-a-quotient-past-the-bound-a-miss
def test_keeps_a_quotient_past_the_bound_a_miss() -> None:
    result = run_pyct(PAST_THE_BOUND, '{"x": 2.0}', "--budget", "30", timeout=60)

    assert result.returncode == 0, result.stderr
    misses = summary_line(result.stdout)["misses"]
    assert isinstance(misses, list), result.stdout
    assert [(miss["line"], miss["col"]) for miss in misses] == [(2, 7)], result.stdout
    assert misses[0]["why"] in ("unknown", "timeout"), result.stdout
    xs = [x_of(line) for line in input_lines(result.stdout)]
    assert all(x // 1.0 != 1e300 for x in xs), result.stdout


# solve-a-finite-floor-division-fast-keeps-a-floor-no-double-has-unsat
def test_keeps_a_floor_no_double_has_unsat() -> None:
    result = run_pyct(NO_DOUBLE_HAS, '{"x": 2.0}', "--budget", "30", timeout=60)

    assert result.returncode == 0, result.stderr
    misses = summary_line(result.stdout)["misses"]
    assert isinstance(misses, list), result.stdout
    assert [(miss["line"], miss["col"], miss["why"]) for miss in misses] == [(2, 7, "unsat")]
    assert "solver: 0 sat, 1 unsat, 0 unknown, 0 timeout" in result.stderr.splitlines()


# solve-a-finite-floor-division-fast-stays-inside-the-solver-limit
def test_stays_inside_the_solver_limit() -> None:
    _, stdout, stderr = timed_run("--solver-timeout", "0.01")

    site = f"{FLOAT_POSITION_FILE}:{FINITE_FORK[0]}:{FINITE_FORK[1]}"
    assert f"missed {site} timeout" in stderr.splitlines(), stderr
    assert aimed_at(stdout, FINITE_FORK) == [], stdout
    assert "stopped: no fork to flip" in stderr.splitlines(), stderr
