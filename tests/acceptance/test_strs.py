"""Acceptance tests for the follow-string-compares and follow-string-search children of the
follow-strings story.

Each test spawns ``python -P -m pyct`` through the harness, the way the follow-integers
tests do: an operation is followed only if the fork it built reaches the solver and the
solver's answer runs, so only a real run through the command line proves it.
"""

from tests.acceptance.harness import (
    REPO_ROOT,
    first_line,
    input_lines,
    one_line,
    run_pyct,
    summary_line,
    two_lines,
)

EQUALITY = "targets.strs.equality::greet"
EQUALITY_FILE = str(REPO_ROOT / "targets" / "strs" / "equality.py")
UNANNOTATED = "targets.strs.unannotated::greet"
SPECIAL_CHARACTERS = "targets.strs.special_characters::match"
# the literal the target compares against, as the fixture's source spells it
SPECIAL_LITERAL = 'a\nb"c\\d é'
MIXED_EQUALITY = "targets.strs.mixed_equality::count"
ORDERED_WITH_NUMBER = "targets.strs.ordered_with_number::rank"
SIX_COMPARES = "targets.strs.six_compares::count"
SIX_COMPARES_FILE = str(REPO_ROOT / "targets" / "strs" / "six_compares.py")
# the line of each compare in ``count``, and every line of it but its ``def``
COMPARE_LINES = [3, 5, 7, 9, 11, 13]
COUNT_LINES = list(range(2, 16))
TRUTH_TEST = "targets.strs.truth_test::tell"
TRUTH_TEST_FILE = str(REPO_ROOT / "targets" / "strs" / "truth_test.py")
PAST_THE_LAST_CHARACTER = "targets.strs.past_the_last_character::match"
ENCODE_CHECK = "targets.strs.encode_check::check"
TEXT_CONVERSION = "targets.strs.text_conversion::show"
LENGTH_CHECK = "targets.strs.length_check::check"
FIND_FROM_POSITION = "targets.strs.find_from_position::check"
FIND_BELOW = "targets.strs.find_below::check"
IN_WHERE_IT_RUNS = "targets.strs.in_where_it_runs::look"
IN_WHERE_IT_RUNS_FILE = str(REPO_ROOT / "targets" / "strs" / "in_where_it_runs.py")


def text(line: dict[str, object], name: str) -> str:
    """One str argument off a printed line, narrowed so the comparison means something."""
    args = line["args"]
    assert isinstance(args, dict), line
    value = args[name]
    assert isinstance(value, str), line
    return value


def number(line: dict[str, object], name: str) -> int:
    """One int argument off a printed line, narrowed so the comparison means something."""
    args = line["args"]
    assert isinstance(args, dict), line
    value = args[name]
    assert isinstance(value, int), line
    return value


def forks_of(line: dict[str, object]) -> list[dict[str, object]]:
    """The forks off a printed line, narrowed so a field lookup means something."""
    forks = line["forks"]
    assert isinstance(forks, list), line
    return [dict(fork) for fork in forks]


def followed(stdout: str) -> list[tuple[object, list[tuple[object, object]]]]:
    """Each input's arguments and the forks it took, with nothing that names the file."""
    return [
        (line["args"], [(fork["expression"], fork["taken"]) for fork in forks_of(line)])
        for line in input_lines(stdout)
    ]


def covered_of(lines: list[dict[str, object]]) -> dict[str, list[int]]:
    """Every input's covered map added up, written the way a printed line writes one."""
    union: dict[str, set[int]] = {}
    for line in lines:
        covered = line["covered"]
        assert isinstance(covered, dict), line
        for file, numbers in covered.items():
            union[str(file)] = union.get(str(file), set()) | {int(n) for n in numbers}
    return {file: sorted(numbers) for file, numbers in union.items()}


# follow-strings-flips-a-string-equality
def test_flips_a_string_equality() -> None:
    result = run_pyct(EQUALITY, '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    # the literal carries its Python quotes, so it reads apart from the parameter's name
    fork = {"file": EQUALITY_FILE, "line": 2, "col": 7, "expression": ["==", "s", "'abc'"]}
    assert forks_of(seed) == [{**fork, "taken": False}]
    assert forks_of(solved) == [{**fork, "taken": True}]
    assert text(solved, "s") == "abc"
    assert covered_of([seed, solved]) == {EQUALITY_FILE: [2, 3, 4]}


# follow-strings-follows-every-string-compare
def test_follows_every_string_compare() -> None:
    result = run_pyct(SIX_COMPARES, '{"s": "a"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # each compare is its own fork, written under the operator the target wrote
    assert [fork["expression"] for fork in forks_of(inputs[0])] == [
        ["<", "s", "'b'"],
        ["<=", "s", "'c'"],
        [">", "s", "'d'"],
        [">=", "s", "'e'"],
        ["==", "s", "'f'"],
        ["!=", "s", "'g'"],
    ]
    # every fork is flipped: some input takes each side of each compare, and every input the
    # solver handed back took the side it was aimed at
    sides = {(fork["line"], fork["taken"]) for line in inputs for fork in forks_of(line)}
    assert sides == {(line, taken) for line in COMPARE_LINES for taken in (True, False)}
    assert [line["mismatch_at"] for line in inputs[1:]] == [None] * (len(inputs) - 1)
    assert covered_of(inputs) == {SIX_COMPARES_FILE: COUNT_LINES}
    summary = summary_line(result.stdout)
    # a fork the solver gave no input for is one whose other side no input can take: unsat,
    # never a question the solver ran out of time on
    solver = summary["solver"]
    assert isinstance(solver, dict), summary
    assert (solver["unknown"], solver["timeout"]) == (0, 0)
    assert summary["stopped"] == "no fork to flip"


# follow-strings-follows-the-truth-test
def test_follows_the_truth_test() -> None:
    result = run_pyct(TRUTH_TEST, '{"s": "abc"}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    # `if not s:` tests s for truth, and the empty string is the one value on the other side
    assert [fork["expression"] for fork in forks_of(seed)] == [["!=", "s", "''"]]
    assert [fork["taken"] for fork in forks_of(seed)] == [True]
    assert seed["downgrades"] == []
    assert text(solved, "s") == ""
    assert [fork["taken"] for fork in forks_of(solved)] == [False]
    assert covered_of([seed, solved]) == {TRUTH_TEST_FILE: [2, 3, 4]}


# follow-strings-prints-the-fork-in-infix-on-stderr
def test_prints_the_fork_in_infix_on_stderr() -> None:
    result = run_pyct(EQUALITY, '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    # the literal keeps the quotes it has on the stdout line, so the name reads apart from it
    assert f"fork {EQUALITY_FILE}:2:7  s == 'abc'  not taken" in result.stderr.splitlines()


# follow-strings-round-trips-a-literal-with-special-characters
def test_round_trips_a_literal_with_special_characters() -> None:
    result = run_pyct(SPECIAL_CHARACTERS, '{"s": ""}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    # a newline, both quotes, a backslash, a space and a character past ASCII all reach the
    # solver and come back as the same characters
    assert text(solved, "s") == SPECIAL_LITERAL
    assert [fork["expression"] for fork in forks_of(seed)] == [["==", "s", repr(SPECIAL_LITERAL)]]
    assert [fork["taken"] for fork in forks_of(solved)] == [True]


# follow-strings-tracks-an-int-made-from-a-string
def test_tracks_an_int_made_from_a_string() -> None:
    result = run_pyct(FIND_BELOW, '{"s": "abc", "n": 1}')

    assert result.returncode == 0, result.stderr
    seed, solved = two_lines(result.stdout)
    # find answers with a tracked int, so its compare with n is one fork on both parameters
    expression = ["<", ["find", "s", "'x'"], "n"]
    assert [(fork["expression"], fork["taken"]) for fork in forks_of(seed)] == [(expression, True)]
    assert [(fork["expression"], fork["taken"]) for fork in forks_of(solved)] == [
        (expression, False)
    ]
    assert solved["mismatch_at"] is None
    # the solver may change s, n, or both; Python has to agree the input takes the other side
    assert text(solved, "s").find("x") >= number(solved, "n")


# follow-strings-downgrades-a-literal-the-solver-cannot-hold
def test_downgrades_a_literal_the_solver_cannot_hold() -> None:
    result = run_pyct(PAST_THE_LAST_CHARACTER, '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    # U+30000 is one past the last character cvc5 holds, so Python answers the compare alone
    assert seed["downgrades"] == [{"name": "__eq__", "count": 1}]
    assert seed["forks"] == []
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# follow-strings-reads-the-type-from-the-seed
def test_reads_the_type_from_the_seed() -> None:
    bare = run_pyct(UNANNOTATED, '{"s": "x"}')
    annotated = run_pyct(EQUALITY, '{"s": "x"}')

    assert bare.returncode == 0, bare.stderr
    # the seed's value is a str, so the bare target is followed the way the annotated one is:
    # the same inputs, each taking the same side of the same fork
    assert followed(bare.stdout) == followed(annotated.stdout)
    _, solved = two_lines(bare.stdout)
    assert text(solved, "s") == "abc"


# follow-strings-treats-a-mixed-equality-as-plain
def test_treats_a_mixed_equality_as_plain() -> None:
    result = run_pyct(MIXED_EQUALITY, '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    # Python answers a str against an int with a constant, so nothing forks and nothing is lost
    assert seed["forks"] == []
    assert seed["downgrades"] == []
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# follow-strings-records-an-untaught-method-as-a-downgrade
def test_records_an_untaught_method_as_a_downgrade() -> None:
    result = run_pyct(ENCODE_CHECK, '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    # a method is named by its own name, and what it hands back is plain, so nothing forks on it
    assert seed["downgrades"] == [{"name": "encode", "count": 1}]
    assert seed["forks"] == []


# follow-strings-counts-text-conversion-as-a-downgrade
def test_counts_text_conversion_as_a_downgrade() -> None:
    result = run_pyct(TEXT_CONVERSION, '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    # str(s) runs __str__; an f-string with no format spec runs __format__, which runs
    # __str__ first, so the two __str__ calls in a row are one entry
    assert seed["downgrades"] == [
        {"name": "__str__", "count": 2},
        {"name": "__format__", "count": 1},
    ]


# follow-strings-counts-len-as-a-downgrade
def test_counts_len_as_a_downgrade() -> None:
    result = run_pyct(LENGTH_CHECK, '{"s": "abc"}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    # Python makes what __len__ hands back a plain int before the target sees it
    assert seed["downgrades"] == [{"name": "__len__", "count": 1}]
    assert seed["forks"] == []


# follow-strings-records-in-where-it-runs
def test_records_in_where_it_runs() -> None:
    result = run_pyct(IN_WHERE_IT_RUNS, '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    # Python makes the answer of `in` a plain bool where the `in` runs, so the fork is on the
    # `y =` line and `if y:` tests a plain bool; `not in` is the same fork with the side reversed
    assert forks_of(seed) == [
        {
            "file": IN_WHERE_IT_RUNS_FILE,
            "line": 2,
            "col": 8,
            "expression": ["in", "'a'", "s"],
            "taken": False,
        },
        {
            "file": IN_WHERE_IT_RUNS_FILE,
            "line": 5,
            "col": 7,
            "expression": ["in", "'b'", "s"],
            "taken": False,
        },
    ]


# follow-strings-downgrades-a-search-from-a-position
def test_downgrades_a_search_from_a_position() -> None:
    result = run_pyct(FIND_FROM_POSITION, '{"s": "abcx"}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    # a start position is a form pyct does not encode, so str answers and the method is named
    assert seed["downgrades"] == [{"name": "find", "count": 1}]
    assert seed["forks"] == []


# follow-strings-reports-an-ordered-compare-with-a-number
def test_reports_an_ordered_compare_with_a_number() -> None:
    result = run_pyct(ORDERED_WITH_NUMBER, '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    # the detail is CPython's own sentence, so only the kind and the name are pyct's to pin
    failure = seed["failure"]
    assert isinstance(failure, dict), seed
    assert failure["kind"] == "target_raised"
    assert str(failure["detail"]).startswith("TypeError:")
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"
