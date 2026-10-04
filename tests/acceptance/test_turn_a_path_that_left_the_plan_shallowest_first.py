"""Acceptance tests for the turn-a-path-that-left-the-plan-shallowest-first ticket.

Each test spawns ``python -P -m pyct`` through the harness with the real cvc5. The fixtures in
``targets/flip/past_a_cache.py`` pass equal values to an ``lru_cache`` in another module, which
compares two keys only when their hashes match: a flip of one such compare gives a value whose
hash differs, so the compare never runs and the input leaves the plan, covering no new line of
the fixture's file. ``targets/flip/flips_gain_nothing.py`` holds checks whose flips reach their
plans and cover no new line.

``covers-elliptic-curve`` and ``loses-no-row`` are measured on sympy and the compare tool, and
their evidence is in the pull request.
"""

from tests.acceptance.harness import REPO_ROOT, input_lines, run_pyct, summary_line

PAST_A_CACHE = "targets.flip.past_a_cache"
PAST_A_CACHE_FILE = str(REPO_ROOT / "targets" / "flip" / "past_a_cache.py")
GAIN_NOTHING = "targets.flip.flips_gain_nothing"
# `return 0` under `if m == 0:` in `curve`, which the seed's m of 1 does not run
CURVE_NO_MODULUS = 9
# `return "apart"` in `apart`, which only an input whose two numbers missed the cache runs
APART = 24
# the first word of each line of the trace a run writes on stderr, but for an indented detail
TRACE_KINDS = {
    "seed",
    "solver",
    "aim",
    "reached",
    "left",
    "fork",
    "covered",
    "ended",
    "downgrades",
    "missed",
    "solver:",
    "uncovered",
    "why",
    "stopped:",
}


def solver_lines(stdout: str) -> list[dict[str, object]]:
    """The printed lines of the inputs the solver answered, in run order."""
    return [line for line in input_lines(stdout) if line["source"] == "solver"]


def aim_of(line: dict[str, object]) -> dict[str, object]:
    aim = line["aim"]
    assert isinstance(aim, dict), line
    return aim


def positions(stdout: str) -> list[object]:
    """The position each solver input was aimed at, in run order."""
    return [aim_of(line)["position"] for line in solver_lines(stdout)]


def covered_in_fixture(line: dict[str, object]) -> set[int]:
    covered = line["covered"]
    assert isinstance(covered, dict), line
    return set(covered.get(PAST_A_CACHE_FILE, []))


# turn-a-path-that-left-the-plan-shallowest-first-reaches-a-shallow-fork-past-a-cache
def test_a_leave_without_gain_sends_the_next_pick_past_the_cache_to_the_first_fork() -> None:
    seed = '{"m": 1, "a": 0, "b": 0, "c": 0, "d": 0, "e": 0, "f": 0}'

    result = run_pyct(f"{PAST_A_CACHE}::curve", seed, "--plateau", "5")

    assert result.returncode == 0, result.stderr
    summary = summary_line(result.stdout)
    uncovered = summary["uncovered"]
    assert isinstance(uncovered, dict), summary
    assert CURVE_NO_MODULUS not in uncovered.get(PAST_A_CACHE_FILE, []), result.stdout
    solved = solver_lines(result.stdout)
    left = next(at for at, line in enumerate(solved) if line["mismatch_at"] is not None)
    assert aim_of(solved[left + 1]) == {
        "file": PAST_A_CACHE_FILE,
        "line": 8,
        "col": 7,
        "position": 0,
    }, result.stdout


# turn-a-path-that-left-the-plan-shallowest-first-keeps-deepest-first-on-reached-plans
def test_inputs_that_reach_their_plans_keep_the_deepest_fork_first() -> None:
    result = run_pyct(f"{GAIN_NOTHING}::three_deep", '{"x": 30}')

    assert result.returncode == 0, result.stderr
    assert all(line["mismatch_at"] is None for line in solver_lines(result.stdout)), result.stdout
    assert positions(result.stdout) == [2, 1, 0], result.stdout


# turn-a-path-that-left-the-plan-shallowest-first-keeps-deepest-first-after-a-leave-that-gains
def test_a_leave_that_covers_a_new_line_keeps_the_deepest_fork_first() -> None:
    result = run_pyct(f"{PAST_A_CACHE}::apart", '{"m": 2, "a": 0, "b": 0}')

    assert result.returncode == 0, result.stderr
    first = solver_lines(result.stdout)[0]
    assert first["mismatch_at"] is not None, result.stdout
    assert APART in covered_in_fixture(first), result.stdout
    assert positions(result.stdout)[:2] == [2, 1], result.stdout


# turn-a-path-that-left-the-plan-shallowest-first-turns-a-path-once
def test_a_turned_path_stays_shallowest_first_after_more_leaves() -> None:
    result = run_pyct(f"{PAST_A_CACHE}::numbers", '{"a": 0, "b": 0, "c": 0, "d": 0, "e": 0}')

    assert result.returncode == 0, result.stderr
    solved = solver_lines(result.stdout)
    # the first three each leave the plan and cover nothing new
    assert all(line["mismatch_at"] is not None for line in solved[:3]), result.stdout
    assert positions(result.stdout)[:4] == [3, 0, 1, 2], result.stdout


# turn-a-path-that-left-the-plan-shallowest-first-turns-only-the-picked-path
def test_a_turn_leaves_the_leaving_input_s_own_path_deepest_first() -> None:
    seed = '{"m": 2, "a": 0, "b": 0, "x": 0, "y": 0}'

    result = run_pyct(f"{PAST_A_CACHE}::tail", seed)

    assert result.returncode == 0, result.stderr
    first = solver_lines(result.stdout)[0]
    assert first["mismatch_at"] is not None, result.stdout
    # the seed's path shallowest first after the leave, then the leaving input's two forks on
    # line 33, the deeper first
    assert positions(result.stdout)[:5] == [2, 0, 1, 3, 2], result.stdout


# turn-a-path-that-left-the-plan-shallowest-first-prints-nothing-new
def test_a_turn_prints_no_line_or_field_of_its_own() -> None:
    seed = '{"m": 1, "a": 0, "b": 0, "c": 0, "d": 0, "e": 0, "f": 0}'
    plain = run_pyct(f"{GAIN_NOTHING}::three_deep", '{"x": 30}')

    result = run_pyct(f"{PAST_A_CACHE}::curve", seed, "--plateau", "5")

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert {frozenset(line) for line in inputs} == {frozenset(input_lines(plain.stdout)[0])}
    assert set(summary_line(result.stdout)) == set(summary_line(plain.stdout))
    solver = summary_line(result.stdout)["solver"]
    assert isinstance(solver, dict) and set(solver) == {"sat", "unsat", "unknown", "timeout"}
    trace = {line.split(" ", 1)[0] for line in result.stderr.splitlines() if line[:1] != " "}
    assert trace <= TRACE_KINDS, result.stderr


# turn-a-path-that-left-the-plan-shallowest-first-a-miss-turns-nothing
def test_an_unsat_miss_keeps_the_deepest_fork_first() -> None:
    result = run_pyct(f"{GAIN_NOTHING}::implied_deepest", '{"x": 30}')

    assert result.returncode == 0, result.stderr
    misses = summary_line(result.stdout)["misses"]
    assert isinstance(misses, list) and len(misses) == 1, result.stdout
    assert positions(result.stdout) == [1, 0], result.stdout


# turn-a-path-that-left-the-plan-shallowest-first-turns-after-a-failing-input
def test_a_leave_that_raised_turns_its_path_in_a_process_of_its_own_and_in_pyct_s() -> None:
    seed = '{"m": 1, "a": 0, "b": 0, "c": 0}'

    for where in ((), ("--in-process",)):
        result = run_pyct(f"{PAST_A_CACHE}::strict", seed, *where)

        assert result.returncode == 0, result.stderr
        solved = solver_lines(result.stdout)
        assert solved[0]["mismatch_at"] is not None, result.stdout
        assert solved[0]["failure"] is not None, result.stdout
        assert aim_of(solved[1])["position"] == 0, result.stdout
