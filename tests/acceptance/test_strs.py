"""Acceptance tests for the follow-string-compares child of the follow-strings story.

Each test spawns ``python -P -m pyct`` through the harness, the way the follow-integers
tests do: a compare is followed only if the fork it built reaches the solver and the
solver's answer runs, so only a real run through the command line proves it.
"""

from tests.acceptance.harness import (
    REPO_ROOT,
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


def text(line: dict[str, object], name: str) -> str:
    """One str argument off a printed line, narrowed so the comparison means something."""
    args = line["args"]
    assert isinstance(args, dict), line
    value = args[name]
    assert isinstance(value, str), line
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
