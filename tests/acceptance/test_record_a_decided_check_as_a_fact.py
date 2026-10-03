"""Acceptance tests for the record-a-decided-check-as-a-fact story.

A check whose answer a tracked dict already knows, a walk pass the dict's fewest keys reach, its
truth once it holds a key, or a second lookup of a key the path settled, is a fact of the path,
not a fork: no input line lists it, pyct never aims at it, and see-why counts it as decided.
Each test runs pyct through the command line, as a person or sweep reads it.
"""

import pytest

from tests.acceptance.harness import (
    REPO_ROOT,
    first_line,
    forks_of,
    input_lines,
    lines_expressions_and_sides,
    run_pyct,
    summary_line,
)
from tests.acceptance.test_bools import at
from tests.acceptance.test_pass_keywords_through_a_downgrade import covered_in
from tests.acceptance.test_read_a_tracked_value_s_type_as_its_base_type import line_of
from tests.acceptance.test_see_why_a_line_was_missed import NO_TRIES, condition, entry_for

DECIDED = "targets.dicts.decided"
FILE = REPO_ROOT / "targets" / "dicts" / "decided.py"
F = str(FILE)
GROWN = ["+", ["len", "d"], 1]
STORED_A = ["in", "'a'", "d"]


def missed(stderr: str) -> list[str]:
    """The stderr lines that name a fork the solver gave no input for."""
    return [line for line in stderr.splitlines() if line.startswith("missed ")]


def solver_lines(stdout: str) -> list[dict[str, object]]:
    return [line for line in input_lines(stdout) if line["source"] == "solver"]


def args_of(line: dict[str, object]) -> dict[str, object]:
    args = line["args"]
    assert isinstance(args, dict), line
    return args


def covered(stdout: str, file: str = F) -> set[int]:
    """Every line some input covered in one file."""
    return {number for line in input_lines(stdout) for number in covered_in(line, file)}


def tries(entry: dict[str, object]) -> dict[str, object]:
    found = entry["tries"]
    assert isinstance(found, dict), entry
    return found


# record-a-decided-check-as-a-fact-walks-past-a-store-with-no-unsat
def test_walks_past_a_store_with_no_unsat() -> None:
    result = run_pyct(f"{DECIDED}::store_walk", '{"d": {}}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    stored = line_of(FILE, 'd["a"] = 0', "store_walk")
    walked = line_of(FILE, "for k in d:", "store_walk")
    more = line_of(FILE, 'return "more"', "store_walk")
    inputs = input_lines(result.stdout)
    seed = lines_expressions_and_sides(inputs[0])
    assert (stored, STORED_A, False) in seed
    assert (walked, [">", GROWN, 1], False) in seed
    for line in inputs:
        assert [">", GROWN, 0] not in at(line, walked), line
        if (stored, STORED_A, True) in lines_expressions_and_sides(line):
            assert [">", ["len", "d"], 0] not in at(line, walked), line
    solved = solver_lines(result.stdout)
    assert any(more in covered_in(line, F) for line in solved), solved
    assert all(line["mismatch_at"] is None for line in solved), solved
    assert not [line for line in missed(result.stderr) if line.endswith(" unsat")], result.stderr


# record-a-decided-check-as-a-fact-walks-past-a-tracked-store-with-no-unsat
def test_walks_past_a_tracked_store_with_no_unsat() -> None:
    seed = '{"n": "pyct1", "d": {}}'
    result = run_pyct(f"{DECIDED}::tracked_store_walk", seed, "--budget", "5")

    assert result.returncode == 0, result.stderr
    for line in input_lines(result.stdout):
        assert [">", GROWN, 0] not in [fork["expression"] for fork in forks_of(line)], line
    assert not [line for line in missed(result.stderr) if line.endswith(" unsat")], result.stderr


# the bool line, if any, the `if` line and the line under it, of each target
TESTED = {
    "targets.dicts.truth_kept::changed_before": ("ok = bool(", "if ok:", 'return "filled"'),
    f"{DECIDED}::store_truth": (None, "if config:", "return 1"),
}


# record-a-decided-check-as-a-fact-tests-a-changed-dict-as-decided
@pytest.mark.parametrize("target", list(TESTED))
@pytest.mark.parametrize("where", [(), ("--in-process",)], ids=["own-process", "in-process"])
def test_tests_a_changed_dict_as_decided(target: str, where: tuple[str, ...]) -> None:
    result = run_pyct(target, '{"config": {}}', "--budget", "10", *where)

    assert result.returncode == 0, result.stderr
    module, function = target.split("::")
    file = REPO_ROOT / f"{module.replace('.', '/')}.py"
    called, tested, under = TESTED[target]
    stored = line_of(file, 'config["a"] = 0', function)
    seed = first_line(result.stdout)
    assert (stored, ["in", "'a'", "config"], False) in lines_expressions_and_sides(seed)
    assert at(seed, line_of(file, tested, function)) == []
    if called is not None:
        assert at(seed, line_of(file, called, function)) == []
    assert line_of(file, under, function) in covered(result.stdout, str(file))
    assert missed(result.stderr) == []
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# record-a-decided-check-as-a-fact-looks-up-a-settled-key-once
def test_looks_up_a_settled_key_once() -> None:
    result = run_pyct(f"{DECIDED}::looked_up_twice", '{"d": {}}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    first = line_of(FILE, 'if "a" in d:', "looked_up_twice")
    second = line_of(FILE, 'if "a" in d:', "looked_up_twice") + 2
    added = {line_of(FILE, "n += 1", "looked_up_twice"), line_of(FILE, "n += 2", "looked_up_twice")}
    seed = first_line(result.stdout)
    assert (first, STORED_A, False) in lines_expressions_and_sides(seed)
    assert at(seed, second) == []
    found = [
        line
        for line in solver_lines(result.stdout)
        if (first, STORED_A, True) in lines_expressions_and_sides(line)
        and at(line, second) == []
        and added <= set(covered_in(line, F))
    ]
    assert found, result.stdout
    assert missed(result.stderr) == []


# record-a-decided-check-as-a-fact-says-why-a-decided-side-is-never-taken
def test_says_why_a_decided_side_is_never_taken() -> None:
    result = run_pyct(f"{DECIDED}::store_truth", '{"config": {}}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    tested = line_of(FILE, "if config:", "store_truth")
    empty = line_of(FILE, "return 0", "store_truth")
    inputs = summary_line(result.stdout)["inputs"]
    entry = entry_for(result.stdout, empty)
    assert entry["reason"] == "not taken"
    assert entry["condition"] == condition(F, tested, 7, False)
    assert tries(entry) == {**NO_TRIES, "decided": inputs}
    # every `tries` object carries `decided`, after `left_the_plan`
    assert list(tries(entry)) == [*NO_TRIES]
    why = f"why {empty} in {F}: {F}:{tested}:7 never false: {inputs} decided"
    assert why in result.stderr.splitlines(), result.stderr
    assert not [line for line in missed(result.stderr) if f"{F}:{tested}:" in line]


# record-a-decided-check-as-a-fact-keeps-a-fork-the-path-leaves-open
def test_keeps_a_fork_the_path_leaves_open() -> None:
    result = run_pyct(f"{DECIDED}::store_if_flag", '{"flag": false, "d": {}}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    tested = line_of(FILE, "if d:", "store_if_flag")
    inputs = input_lines(result.stdout)
    seed = lines_expressions_and_sides(inputs[0])
    assert (tested, ["!=", ["len", "d"], 0], False) in seed
    flagged = [line for line in inputs if args_of(line)["flag"] is True]
    assert flagged, inputs
    assert all(at(line, tested) == [] for line in flagged), flagged
    returns = {
        line_of(FILE, "return 1", "store_if_flag"),
        line_of(FILE, "return 0", "store_if_flag"),
    }
    assert returns <= covered(result.stdout)
    assert missed(result.stderr) == []


# record-a-decided-check-as-a-fact-keeps-a-fork-a-removal-leaves-open
def test_keeps_a_fork_a_removal_leaves_open() -> None:
    result = run_pyct(f"{DECIDED}::removed_truth", '{"d": {"a": 1, "b": 2}}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    removed = line_of(FILE, 'del d["a"]', "removed_truth")
    tested = line_of(FILE, "if d:", "removed_truth")
    empty = line_of(FILE, "return 0", "removed_truth")
    fork = ["!=", ["-", ["len", "d"], 1], 0]
    seed = lines_expressions_and_sides(first_line(result.stdout))
    assert (removed, STORED_A, True) in seed
    assert (tested, fork, True) in seed
    solved = solver_lines(result.stdout)
    assert any(
        (tested, fork, False) in lines_expressions_and_sides(line) and empty in covered_in(line, F)
        for line in solved
    ), solved


# record-a-decided-check-as-a-fact-decides-by-a-key-the-path-found
def test_decides_by_a_key_the_path_found() -> None:
    result = run_pyct(f"{DECIDED}::found_truth", '{"d": {"a": 1}}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    looked = line_of(FILE, 'if "a" in d:', "found_truth")
    tested = line_of(FILE, "if d:", "found_truth")
    seed = first_line(result.stdout)
    assert (looked, STORED_A, True) in lines_expressions_and_sides(seed)
    assert at(seed, tested) == []
    solved = solver_lines(result.stdout)
    nothing = line_of(FILE, "return 0", "found_truth")
    assert any(
        "a" not in args_of(line)["d"] and nothing in covered_in(line, F)  # type: ignore[operator]
        for line in solved
    ), solved
    entry = entry_for(result.stdout, line_of(FILE, "return 2", "found_truth"))
    assert entry["reason"] == "not taken"
    assert entry["condition"] == condition(F, tested, 11, False)
    decided = tries(entry)["decided"]
    assert isinstance(decided, int) and decided > 0, entry


# record-a-decided-check-as-a-fact-keeps-a-shared-key-s-place
def test_keeps_a_shared_key_s_place() -> None:
    file = str(REPO_ROOT / "targets" / "dicts" / "settled.py")
    result = run_pyct("targets.dicts.settled::int_only", '{"d": {"1": 9}}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    assert 12 not in covered(result.stdout, file)
    # the walk hands out the shared key 1, so `d[k]` on line 10 looks it up after a fact of the
    # walk's place, and the flip of that lookup's fork is unknown, as at the base; `d[k] > 5`
    # shares its site, and its flip on the seed's path is sat. Line 11 looks the settled key up
    # again, a fact
    trace = missed(result.stderr)
    assert f"missed {file}:10:11 unknown" in trace, result.stderr
    assert not [line for line in trace if line.startswith(f"missed {file}:11:")], result.stderr


# record-a-decided-check-as-a-fact-counts-positions-over-forks
def test_counts_positions_over_forks() -> None:
    result = run_pyct(f"{DECIDED}::store_walk", '{"d": {}}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    reached = [line for line in solver_lines(result.stdout) if line["mismatch_at"] is None]
    assert reached, result.stdout
    for line in reached:
        aim = line["aim"]
        assert isinstance(aim, dict), line
        fork = forks_of(line)[aim["position"]]
        assert (fork["file"], fork["line"], fork["col"]) == (aim["file"], aim["line"], aim["col"])


# each target the solver's own unsat reads, its seed, the misses the base prints, and the line
# see-why names with the unsat count the base gives it, if any
OWN_UNSAT = [
    ("targets.why.untaken::same", '{"x": 2}', ["3:7"], (4, 1)),
    ("targets.flip.implied_check::narrow", '{"x": 3}', ["3:11"], (5, 1)),
    ("targets.flip.repeated_check::thrice", '{"x": 0}', ["4:11"] * 4, None),
]


# record-a-decided-check-as-a-fact-leaves-the-solver-s-own-unsat
@pytest.mark.parametrize(("target", "seed", "sites", "why"), OWN_UNSAT, ids=lambda v: str(v)[:20])
def test_leaves_the_solver_s_own_unsat(
    target: str, seed: str, sites: list[str], why: tuple[int, int] | None
) -> None:
    result = run_pyct(target, seed, "--budget", "10")

    assert result.returncode == 0, result.stderr
    module = target.split("::")[0]
    file = str(REPO_ROOT / f"{module.replace('.', '/')}.py")
    assert missed(result.stderr) == [f"missed {file}:{site} unsat" for site in sites]
    if why is not None:
        line, unsat = why
        entry = entry_for(result.stdout, line)
        assert entry["reason"] == "not taken"
        assert tries(entry) == {**NO_TRIES, "unsat": unsat, "decided": 0}


# record-a-decided-check-as-a-fact-keeps-a-dying-input-s-facts
def test_keeps_a_dying_input_s_facts() -> None:
    result = run_pyct(f"{DECIDED}::store_then_die", '{"config": {}}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    tested = line_of(FILE, "if config:", "store_then_die")
    inputs = input_lines(result.stdout)
    for line in inputs:
        assert line["failure"] == {"kind": "crashed", "detail": "killed by SIGKILL"}, line
        assert at(line, tested) == [], line
    entry = entry_for(result.stdout, line_of(FILE, "return 1", "store_then_die"))
    assert entry["reason"] == "not taken"
    assert entry["condition"] == condition(F, tested, 7, False)
    assert tries(entry)["decided"] == summary_line(result.stdout)["inputs"]


# a change pyct answers without a fork, as one under a tracked key, may touch any key on another
# input: no lookup after it is decided, and the fewest keys count only what holds whichever key
# it touched
# (record-a-decided-check-as-a-fact, review round 1: unforked-dict-change-read-as-decided)
def test_a_lookup_after_a_tracked_store_stays_a_fork() -> None:
    seed = '{"n": "pyct1", "d": {}}'
    result = run_pyct(f"{DECIDED}::repeat_after_tracked_store", seed, "--budget", "10")

    assert result.returncode == 0, result.stderr
    again = line_of(FILE, 'if "a" in d:', "repeat_after_tracked_store") + 3
    assert at(first_line(result.stdout), again) == [STORED_A]
    entry = entry_for(result.stdout, line_of(FILE, "return 1", "repeat_after_tracked_store"))
    assert tries(entry)["decided"] == 0, entry


def test_a_walk_after_a_tracked_pop_stays_a_fork() -> None:
    seed = '{"n": "pyct1", "d": {"b": 1}}'
    result = run_pyct(f"{DECIDED}::walk_after_tracked_pop", seed, "--budget", "10")

    assert result.returncode == 0, result.stderr
    # the pop may take a or b on another input, so only one key is known: the second pass
    # is a fork
    walked = line_of(FILE, "for k in d:", "walk_after_tracked_pop")
    assert [">", ["+", ["len", "d"], 1], 1] in at(first_line(result.stdout), walked)
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


def test_a_truth_test_after_a_tracked_pop_stays_a_fork() -> None:
    seed = '{"n": "pyct1", "d": {"b": 1}}'
    result = run_pyct(f"{DECIDED}::truth_after_tracked_pop", seed, "--budget", "10")

    assert result.returncode == 0, result.stderr
    entry = entry_for(result.stdout, line_of(FILE, "return 2", "truth_after_tracked_pop"))
    assert entry["reason"] == "not taken"
    assert tries(entry)["decided"] == 0, entry


def test_a_truth_test_after_a_removal_a_forkless_store_may_feed_stays_a_fork() -> None:
    # n "b" stores the key the pop then removes, so the dict may be empty at the test
    seed = '{"n": "pyct1", "d": {}}'
    result = run_pyct(f"{DECIDED}::removed_after_tracked_store", seed, "--budget", "10")

    assert result.returncode == 0, result.stderr
    entry = entry_for(result.stdout, line_of(FILE, "return 0", "removed_after_tracked_store"))
    assert entry["reason"] == "not taken"
    assert tries(entry)["decided"] == 0, entry


def test_a_truth_test_after_any_removal_on_a_marked_dict_stays_a_fork() -> None:
    # n "b" stores the tuple key the pop then removes, so the dict may be empty at the test
    seed = '{"n": "pyct1", "d": {}}'
    result = run_pyct(f"{DECIDED}::removed_tuple_after_tracked_store", seed, "--budget", "10")

    assert result.returncode == 0, result.stderr
    function = "removed_tuple_after_tracked_store"
    entry = entry_for(result.stdout, line_of(FILE, "return 0", function))
    assert entry["reason"] == "not taken"
    assert tries(entry)["decided"] == 0, entry
