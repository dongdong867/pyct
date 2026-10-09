"""Acceptance tests for the record-decided-checks-on-lists-strings-and-second-walks story.

Each tracked list, string and dict keeps a length range from how it was built and from the
forks its walks, truth tests, indexes and compares recorded. A check that range proves is a
fact, not a fork, and so is a compare of the int `len(x)` returns with a plain int, directly or
through plain `+`, `-` and `*`. Each test runs pyct through the command line, as a person or
sweep reads it.
"""

import json

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
from tests.acceptance.test_record_a_decided_check_as_a_fact import (
    args_of,
    covered,
    missed,
    solver_lines,
)

LISTS = "targets.lists.measured"
STRS = "targets.strs.measured"
DICTS = "targets.dicts.measured"
LISTS_FILE = REPO_ROOT / "targets" / "lists" / "measured.py"
STRS_FILE = REPO_ROOT / "targets" / "strs" / "measured.py"
DICTS_FILE = REPO_ROOT / "targets" / "dicts" / "measured.py"


def unsat(stderr: str) -> list[str]:
    """The `missed` lines that end in `unsat`."""
    return [line for line in missed(stderr) if line.endswith(" unsat")]


def file_of(target: str) -> str:
    module = target.split("::")[0]
    return str(REPO_ROOT / f"{module.replace('.', '/')}.py")


def length_checks(line: dict[str, object], number: int, col: int) -> list[object]:
    """The forks a printed line lists at one site of the target on a length."""
    return [
        fork["expression"]
        for fork in forks_of(line)
        if (fork["line"], fork["col"]) == (number, col)
        and isinstance(fork["expression"], list)
        and isinstance(fork["expression"][1], list)
        and fork["expression"][1][:1] == ["len"]
    ]


def lengths_at(line: dict[str, object], number: int, measured: object) -> list[object]:
    """The forks a printed line lists at one line of the target on one length term."""
    return [
        expression
        for expression in at(line, number)
        if isinstance(expression, list) and ["len", measured] in expression
    ]


# the bool line, if any, the `if` line and the line under it, of each target
TESTED = {
    "targets.lists.truth_kept::changed_before": ("ok = bool(", "if ok:", 'return "filled"'),
    f"{LISTS}::append_truth": (None, "if items:", "return 1"),
}


# record-decided-checks-on-lists-strings-and-second-walks-tests-a-changed-list-as-decided
@pytest.mark.parametrize("target", list(TESTED))
@pytest.mark.parametrize("where", [(), ("--in-process",)], ids=["own-process", "in-process"])
def test_tests_a_changed_list_as_decided(target: str, where: tuple[str, ...]) -> None:
    result = run_pyct(target, '{"items": []}', "--budget", "10", *where)

    assert result.returncode == 0, result.stderr
    file = file_of(target)
    function = target.split("::")[1]
    called, tested, under = TESTED[target]
    seed = first_line(result.stdout)
    assert at(seed, line_of(REPO_ROOT / file, tested, function)) == []
    if called is not None:
        assert at(seed, line_of(REPO_ROOT / file, called, function)) == []
    assert line_of(REPO_ROOT / file, under, function) in covered(result.stdout, file)
    assert missed(result.stderr) == []
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# each walked-twice target, its seed, the walk's own term, and the check inside the second walk
TWICE = {
    f"{LISTS}::walk_twice": ('{"xs": [1, 2]}', "xs", "for x in xs:", "if x == 7:"),
    f"{STRS}::walk_twice": ('{"s": "ab"}', "s", "for c in s:", 'if c == "#":'),
    f"{DICTS}::walk_twice": ('{"d": {"a": 1}}', "d", "for k in d:", 'if k == "zz":'),
}


# record-decided-checks-on-lists-strings-and-second-walks-walks-a-value-again-with-no-unsat
@pytest.mark.serial
@pytest.mark.parametrize("target", list(TWICE))
def test_walks_a_value_again_with_no_unsat(target: str) -> None:
    seed, name, walk, check = TWICE[target]
    result = run_pyct(target, seed, "--budget", "5")

    assert result.returncode == 0, result.stderr
    file = REPO_ROOT / file_of(target)
    first = line_of(file, walk, "walk_twice")
    second = line_of(file, walk, "walk_twice") + 2
    assert line_of(file, check, "walk_twice") == second + 1
    for line in input_lines(result.stdout):
        walked = lines_expressions_and_sides(line)
        passes = [(e, taken) for number, e, taken in walked if number == first]
        assert passes and passes[-1][1] is False, line
        assert all(isinstance(e, list) and e[1] == ["len", name] for e, _ in passes), line
        assert at(line, second) == [], line
    summary = summary_line(result.stdout)
    assert summary["solver"]["unsat"] == 0, summary  # type: ignore[index]
    if target != f"{DICTS}::walk_twice":
        flagged = line_of(file, "return -1", "walk_twice")
        assert any(flagged in covered_in(line, str(file)) for line in solver_lines(result.stdout))


# record-decided-checks-on-lists-strings-and-second-walks-walks-a-string-three-times-with-no-unsat
@pytest.mark.serial
def test_walks_a_string_three_times_with_no_unsat() -> None:
    result = run_pyct("targets.loops.walks::walk_both", '{"s": "xy", "t": "xy"}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    file = str(REPO_ROOT / "targets" / "loops" / "walks.py")
    for line in input_lines(result.stdout):
        sides = lines_expressions_and_sides(line)
        ended = any(
            n == 2 and isinstance(e, list) and e[1] == ["len", "s"] and not taken
            for n, e, taken in sides
        )
        if ended:
            assert lengths_at(line, 4, "s") == [], line
            assert lengths_at(line, 7, "s") == [], line
    assert unsat(result.stderr) == []
    # the base covers every line of the function
    assert covered(result.stdout, file) == set(range(2, 11))


# record-decided-checks-on-lists-strings-and-second-walks-walks-past-what-a-change-added
def test_walks_past_what_a_change_added() -> None:
    listed = run_pyct(f"{LISTS}::append_walk", '{"xs": []}', "--budget", "5")
    joined = run_pyct(f"{STRS}::concat_walk", '{"s": ""}', "--budget", "5")

    assert listed.returncode == 0, listed.stderr
    appended = ["+", "xs", ["[,]", 1]]
    for line in input_lines(listed.stdout):
        assert [">", ["len", appended], 0] not in [f["expression"] for f in forks_of(line)]
    counted = line_of(LISTS_FILE, "n += 1", "append_walk")
    assert any(counted in covered_in(line, str(LISTS_FILE)) for line in solver_lines(listed.stdout))
    assert joined.returncode == 0, joined.stderr
    walk = line_of(STRS_FILE, 'for c in s + "!":', "concat_walk")
    added = ["+", "s", "'!'"]
    for line in input_lines(joined.stdout):
        assert [">", ["len", added], 0] not in [f["expression"] for f in forks_of(line)]
    seed = lines_expressions_and_sides(first_line(joined.stdout))
    assert (walk, [">", ["len", added], 1], False) in seed
    found = line_of(STRS_FILE, "return 1", "concat_walk")
    assert any(found in covered_in(line, str(STRS_FILE)) for line in solver_lines(joined.stdout))


# record-decided-checks-on-lists-strings-and-second-walks-indexes-a-list-the-path-measured
def test_indexes_a_list_the_path_measured() -> None:
    result = run_pyct("targets.nested.two_items::classify", '{"items": [1, 2]}')

    assert result.returncode == 0, result.stderr
    file = str(REPO_ROOT / "targets" / "nested" / "two_items.py")
    seed = first_line(result.stdout)
    sides = lines_expressions_and_sides(seed)
    assert (2, [">", ["len", "items"], 0], True) in sides
    assert (4, [">", ["len", "items"], 1], True) in sides
    assert lengths_at(seed, 6, "items") == []
    assert unsat(result.stderr) == []
    # the base covers every line of the function
    assert covered(result.stdout, file) == set(range(2, 9))


def appended(line: dict[str, object]) -> int:
    """How many items `gather` appended on one input: the positive items of its data."""
    data = args_of(line)["data"]
    assert isinstance(data, list), line
    return sum(1 for item in data if isinstance(item, int) and item > 0)


# record-decided-checks-on-lists-strings-and-second-walks-indexes-a-list-a-change-measured
@pytest.mark.serial
def test_indexes_a_list_a_change_measured() -> None:
    gather = run_pyct(
        "targets.lists.thousands::gather", '{"data": [1, 1, 1, 1, 1], "items": []}', "--budget", "5"
    )
    ordered = run_pyct(
        "targets.lists.changes::sorted_in_place", '{"items": [1, 2, 3, 4, 5, 6]}', "--budget", "5"
    )
    tally = run_pyct("targets.lists.in_place::tally", '{"counts": [0, 0], "n": 3}', "--budget", "5")

    for result in (gather, ordered, tally):
        assert result.returncode == 0, result.stderr
    thousands = str(REPO_ROOT / "targets" / "lists" / "thousands.py")
    for line in input_lines(gather.stdout):
        if appended(line) >= 4:
            assert length_checks(line, 5, 7) + length_checks(line, 7, 7) == [], line
    # the item compare shares the index's site, and its own flip may run out of time on a
    # loaded machine: no flip there is unsat, as the long-enough check's were
    assert not [line for line in unsat(gather.stderr) if f"{thousands}:5:7 " in line]
    changes = str(REPO_ROOT / "targets" / "lists" / "changes.py")
    for line in input_lines(ordered.stdout):
        assert length_checks(line, 88, 7) == [], line
    assert not [line for line in unsat(ordered.stderr) if f"{changes}:88:7 " in line]
    for line in input_lines(tally.stdout):
        # the first pass's read measures the list: no later pass lists the check
        assert len(length_checks(line, 3, 8)) <= 1, line
    assert unsat(tally.stderr) == []
    # the base covers every line of each function
    assert covered(gather.stdout, thousands) == set(range(2, 10))
    assert {86, 87, 88, 89, 90} <= covered(ordered.stdout, changes)
    in_place = str(REPO_ROOT / "targets" / "lists" / "in_place.py")
    assert {2, 3, 4, 5, 6} <= covered(tally.stdout, in_place)


# record-decided-checks-on-lists-strings-and-second-walks-reads-a-row-it-tested
@pytest.mark.serial
def test_reads_a_row_it_tested() -> None:
    result = run_pyct("targets.lists.rows::check", '{"grid": [[]]}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    for line in input_lines(result.stdout):
        assert length_checks(line, 3, 19) == [], line
    assert unsat(result.stderr) == []
    # the base covers every line of the function
    rows = str(REPO_ROOT / "targets" / "lists" / "rows.py")
    assert covered(result.stdout, rows) >= {2, 3, 4, 5}


# record-decided-checks-on-lists-strings-and-second-walks-compares-a-measured-length
# serial: a 5 s run whose last input the budget cuts short leaves the plan there, which a
# parallel run's load makes happen
@pytest.mark.serial
@pytest.mark.parametrize(
    ("target", "seed", "tested"),
    [
        (f"{DICTS}::walked_length", '{"d": {"a": 1}}', "if len(d) > 0:"),
        (f"{STRS}::walked_length", '{"s": "ab"}', "if n >= 2:"),
        (f"{LISTS}::append_length", '{"xs": []}', "if len(xs) > 0:"),
    ],
)
def test_compares_a_measured_length(target: str, seed: str, tested: str) -> None:
    result = run_pyct(target, seed, "--budget", "5")

    assert result.returncode == 0, result.stderr
    file = file_of(target)
    function = target.split("::")[1]
    line = line_of(REPO_ROOT / file, tested, function)
    for printed in input_lines(result.stdout):
        assert at(printed, line) == [], printed
    assert not [entry for entry in missed(result.stderr) if f"{file}:{line}:" in entry]
    filled = line_of(REPO_ROOT / file, "return 1", function)
    empty = line_of(REPO_ROOT / file, "return 0", function)
    if target.startswith(LISTS):
        assert filled in covered_in(first_line(result.stdout), file)
        assert summary_line(result.stdout)["stopped"] == "no fork to flip"
        return
    assert {filled, empty} <= covered(result.stdout, file)
    assert all(printed["mismatch_at"] is None for printed in solver_lines(result.stdout))


# record-decided-checks-on-lists-strings-and-second-walks-asks-a-walked-dict-s-length-with-no-unsat
@pytest.mark.serial
def test_asks_a_walked_dict_s_length_with_no_unsat() -> None:
    target = "targets.dicts.walked_then_asked::check_long"
    result = run_pyct(target, '{"d": {"alpha": 1}}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    for line in input_lines(result.stdout):
        assert length_checks(line, 12, 28) == [], line
    assert unsat(result.stderr) == []
    # the base covers every line of the function
    file = str(REPO_ROOT / "targets" / "dicts" / "walked_then_asked.py")
    assert {10, 11, 12, 13, 14} <= covered(result.stdout, file)


# record-decided-checks-on-lists-strings-and-second-walks-tests-a-walked-dict-by-its-walk
def test_tests_a_walked_dict_by_its_walk() -> None:
    result = run_pyct(f"{DICTS}::walked_truth", '{"d": {}}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    walk = line_of(DICTS_FILE, "for k in d:", "walked_truth")
    tested = line_of(DICTS_FILE, "if d:", "walked_truth")
    filled = line_of(DICTS_FILE, "return 1", "walked_truth")
    seed = first_line(result.stdout)
    assert (walk, [">", ["len", "d"], 0], False) in lines_expressions_and_sides(seed)
    assert at(seed, tested) == []
    keyed = [line for line in solver_lines(result.stdout) if len(args_of(line)["d"]) == 1]  # type: ignore[arg-type]
    assert any(
        at(line, tested) == [] and filled in covered_in(line, str(DICTS_FILE)) for line in keyed
    ), keyed
    assert not [entry for entry in missed(result.stderr) if f"{DICTS_FILE}:{tested}:" in entry]


# record-decided-checks-on-lists-strings-and-second-walks-compares-plain-arithmetic-on-a-measured-length  # noqa: E501
def test_compares_plain_arithmetic_on_a_measured_length() -> None:
    result = run_pyct(f"{LISTS}::length_arithmetic", '{"xs": [1, 2, 3, 4]}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    tests = [
        "if len(xs) - 1 > 3:",
        "if len(xs) * 2 == 8:",
        "if 3 < len(xs):",
        "if 2 + len(xs) <= 4:",
    ]
    lines = [line_of(LISTS_FILE, text, "length_arithmetic") for text in tests]
    for printed in input_lines(result.stdout):
        assert [f for f in forks_of(printed) if f["line"] in lines] == [], printed
    assert not [e for e in missed(result.stderr) for n in lines if f"{LISTS_FILE}:{n}:" in e]
    assert {n + 1 for n in lines} <= covered(result.stdout, str(LISTS_FILE))
    assert all(printed["mismatch_at"] is None for printed in solver_lines(result.stdout))


# record-decided-checks-on-lists-strings-and-second-walks-keeps-an-unproven-length-compare-a-fork
def test_keeps_an_unproven_length_compare_a_fork() -> None:
    dicts = run_pyct(f"{DICTS}::unproven", '{"d": {}, "e": {}}', "--budget", "5")
    lists = run_pyct(f"{LISTS}::unproven", '{"xs": [], "n": 0}', "--budget", "5")

    assert dicts.returncode == 0, dicts.stderr
    seed = first_line(dicts.stdout)
    for text in ("if len(d) - len(e) > 0:", "if len(d) // 2 > 0:", "if len(d) % 2 == 1:"):
        number = line_of(DICTS_FILE, text, "unproven")
        assert [taken for n, _, taken in lines_expressions_and_sides(seed) if n == number] == [
            False
        ], seed
    assert lists.returncode == 0, lists.stderr
    seed = first_line(lists.stdout)
    for text in ("if len(xs) > 2:", "if len(xs) > n:"):
        number = line_of(LISTS_FILE, text, "unproven")
        assert [taken for n, _, taken in lines_expressions_and_sides(seed) if n == number] == [
            False
        ], seed
    returns = {
        line_of(LISTS_FILE, "return 1", "unproven"),
        line_of(LISTS_FILE, "return 2", "unproven"),
    }
    assert returns <= {
        n for line in solver_lines(lists.stdout) for n in covered_in(line, str(LISTS_FILE))
    }


# record-decided-checks-on-lists-strings-and-second-walks-keeps-a-fork-a-tracked-cut-leaves-open
def test_keeps_a_fork_a_tracked_cut_leaves_open() -> None:
    result = run_pyct(f"{LISTS}::cut_after_walk", '{"items": [1, 2], "i": 1}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    tested = line_of(LISTS_FILE, "if items:", "cut_after_walk")
    empty = line_of(LISTS_FILE, "return 0", "cut_after_walk")
    seed = [
        (e, taken)
        for n, e, taken in lines_expressions_and_sides(first_line(result.stdout))
        if n == tested
    ]
    assert len(seed) == 1 and seed[0][1] is True, seed
    fork = seed[0][0]
    assert isinstance(fork, list) and fork[0] == "!=" and fork[1][0] == "len" and fork[2] == 0
    assert any(
        (tested, fork, False) in lines_expressions_and_sides(line)
        and empty in covered_in(line, str(LISTS_FILE))
        for line in solver_lines(result.stdout)
    ), result.stdout


# record-decided-checks-on-lists-strings-and-second-walks-starts-a-renamed-row-with-no-range
def test_starts_a_renamed_row_with_no_range() -> None:
    result = run_pyct(f"{LISTS}::renamed_row", '{"grid": [[1], []], "i": 0}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    tested = line_of(LISTS_FILE, "if row:", "renamed_row")
    second = line_of(LISTS_FILE, "return 2", "renamed_row")
    fork = ["!=", ["len", ["[]", "grid", "i"]], 0]
    assert (tested, fork, True) in lines_expressions_and_sides(first_line(result.stdout))
    assert any(
        (tested, fork, False) in lines_expressions_and_sides(line)
        and second in covered_in(line, str(LISTS_FILE))
        for line in solver_lines(result.stdout)
    ), result.stdout
    start = line_of(LISTS_FILE, "def renamed_row(", None)
    assert set(range(start + 1, start + 7)) <= covered(result.stdout, str(LISTS_FILE))


# record-decided-checks-on-lists-strings-and-second-walks-follows-a-join-after-a-walk
def test_follows_a_join_after_a_walk() -> None:
    result = run_pyct(f"{LISTS}::join_after_walk", '{"parts": ["x", "y"]}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    joined = line_of(LISTS_FILE, 'if "-".join(parts) == "a-b":', "join_after_walk")
    found = line_of(LISTS_FILE, "return 1", "join_after_walk")
    seed = first_line(result.stdout)
    assert [(e, taken) for n, e, taken in lines_expressions_and_sides(seed) if n == joined] == [
        (["==", ["join", "'-'", "parts"], "'a-b'"], False)
    ]
    assert any(
        found in covered_in(line, str(LISTS_FILE)) and line["mismatch_at"] is None
        for line in solver_lines(result.stdout)
    ), result.stdout
    assert all(
        line["failure"] is None or "pyct" not in json.dumps(line["failure"])
        for line in input_lines(result.stdout)
    )


# record-decided-checks-on-lists-strings-and-second-walks-walks-a-long-changed-list
@pytest.mark.serial
def test_walks_a_long_changed_list() -> None:
    seed = json.dumps({"items": [], "data": [1] * 3000})
    result = run_pyct(f"{LISTS}::long_changed", seed, "--budget", "10", timeout=60)

    assert result.returncode == 0, result.stderr
    walk = line_of(LISTS_FILE, "for y in items:", "long_changed")
    first = first_line(result.stdout)
    assert first["failure"] is None, first
    walked = [(e, taken) for n, e, taken in lines_expressions_and_sides(first) if n == walk]
    assert len(walked) == 1 and walked[0][1] is False, walked
    end = walked[0][0]
    # the walk's end, past the 3,000 items the appends put in
    assert isinstance(end, list) and end[0] == ">" and end[2] == 3000, walked


# the `missed … unsat` lines the base prints for each target, by file, line and column
COUNTED = [f"bool_int_text.py:{line}:7" for line in (13, 11, 9) * 2]


# record-decided-checks-on-lists-strings-and-second-walks-leaves-the-solver-s-own-unsat
@pytest.mark.serial
@pytest.mark.parametrize(
    ("target", "seed", "base"),
    [
        ("targets.lists.length_bounds::last", '{"items": [1, 2]}', ["length_bounds.py:2:7"]),
        ("targets.strs.bool_int_text::counted", '{"x": 0}', COUNTED),
        ("targets.lists.million::past_the_limit", '{"items": [0]}', ["million.py:8:7"]),
    ],
)
def test_leaves_the_solver_s_own_unsat(target: str, seed: str, base: list[str]) -> None:
    # the million-item answer takes several seconds on an idle machine
    result = run_pyct(target, seed, timeout=120)

    assert result.returncode == 0, result.stderr
    found = [line.rsplit("/", 1)[-1].removesuffix(" unsat") for line in unsat(result.stderr)]
    assert found == base


# record-decided-checks-on-lists-strings-and-second-walks-decides-an-index-past-a-known-length
@pytest.mark.serial
def test_decides_an_index_past_a_known_length() -> None:
    result = run_pyct(f"{LISTS}::sorted_past", '{"xs": [2, 1]}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    tested = line_of(LISTS_FILE, "if ys[5] > 3:", "sorted_past")
    under = tested + 1
    inputs = input_lines(result.stdout)
    short = [line for line in inputs if len(args_of(line)["xs"]) < 6]  # type: ignore[arg-type]
    assert short, inputs
    for line in short:
        assert "IndexError" in json.dumps(line["failure"]), line
        assert at(line, tested) == [], line
    assert any(
        len(args_of(line)["xs"]) >= 6 and under in covered_in(line, str(LISTS_FILE))  # type: ignore[arg-type]
        for line in solver_lines(result.stdout)
    ), inputs
    why = json.loads(result.stdout.splitlines()[-1]).get("why_uncovered", [])
    assert not [entry for entry in why if under in entry["lines"]], why
