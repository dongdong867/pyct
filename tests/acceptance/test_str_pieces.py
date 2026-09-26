"""Acceptance tests for the follow-string-pieces child of the follow-strings story.

Each test spawns ``python -P -m pyct`` through the harness, as the other string tests do: a
piece is followed only if the fork built on it reaches the solver and the solver's answer
runs, so only a real run through the command line proves it.
"""

from tests.acceptance.harness import (
    REPO_ROOT,
    first_line,
    input_lines,
    one_line,
    run_pyct,
    summary_line,
)
from tests.acceptance.test_strs import forks_of, text

INDEX_AND_SLICE = "targets.strs.index_and_slice::shape"
INDEX_AND_SLICE_FILE = str(REPO_ROOT / "targets" / "strs" / "index_and_slice.py")
# each fork the seed takes in ``shape``, in order: the line, the expression, and the side. An
# index adds its long-enough fork on the line of the compare it feeds; a slice adds none
INDEX_AND_SLICE_FORKS: list[tuple[int, list[object], bool]] = [
    (2, [">", ["len", "s"], 0], True),
    (2, ["==", ["[]", "s", 0], "'a'"], False),
    (4, [">=", ["len", "s"], 1], True),
    (4, ["==", ["[]", "s", -1], "'z'"], False),
    (6, ["==", ["[:]", "s", 1, 3], "'bc'"], False),
    (8, ["==", ["[:]", "s", 2, None], "'cd'"], False),
    (10, ["==", ["[:]", "s", None, -1], "'xy'"], False),
]
PIECES = "targets.strs.pieces::combine"
# each fork the seed takes in ``combine``, in order: the line and the expression
PIECES_FORKS: list[tuple[int, list[object]]] = [
    (2, ["==", ["+", "s", "t"], "'ab'"]),
    (4, ["==", ["replace", "s", "'a'", "'b'"], "'bbc'"]),
    (6, ["==", ["removeprefix", "s", "'x'"], "'yz'"]),
    (8, ["==", ["removesuffix", "s", "'y'"], "'xw'"]),
]
LONG_OR_EMPTY = "targets.strs.long_or_empty::measure"
INDEX_PAST_THE_END = "targets.strs.index_past_the_end::fourth"
INDEX_PAST_THE_END_FILE = str(REPO_ROOT / "targets" / "strs" / "index_past_the_end.py")
TRACKED_INDEX = "targets.strs.tracked_index::pick"


def sides_of(lines: list[dict[str, object]]) -> set[tuple[object, str, object]]:
    """Every (line, expression, side) some input took, the expression written as text."""
    return {
        (fork["line"], repr(fork["expression"]), fork["taken"])
        for line in lines
        for fork in forks_of(line)
    }


def answered_every_fork(stdout: str) -> bool:
    """Whether the solver answered every question, sat or unsat, and never ran out of time."""
    solver = summary_line(stdout)["solver"]
    assert isinstance(solver, dict), stdout
    return (solver["unknown"], solver["timeout"]) == (0, 0)


# follow-strings-follows-index-and-slice
def test_follows_index_and_slice() -> None:
    result = run_pyct(INDEX_AND_SLICE, '{"s": "mnop"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert [
        (fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(inputs[0])
    ] == INDEX_AND_SLICE_FORKS
    # every fork is flipped: some input takes each side of each, and every input the solver
    # handed back took the side it was aimed at. The one side no input can take is `s[-1]`'s
    # empty string, which `s[0]` has already raised on, so the solver answers it unsat
    unreachable = (4, repr([">=", ["len", "s"], 1]), False)
    assert sides_of(inputs) == {
        (line, repr(expression), taken)
        for line, expression, _ in INDEX_AND_SLICE_FORKS
        for taken in (True, False)
    } - {unreachable}
    assert [line["mismatch_at"] for line in inputs[1:]] == [None] * (len(inputs) - 1)
    summary = summary_line(result.stdout)
    assert summary["misses"] == [
        {"file": INDEX_AND_SLICE_FILE, "line": 4, "col": 7, "why": "unsat"}
    ]
    assert answered_every_fork(result.stdout)
    assert summary["stopped"] == "no fork to flip"


# follow-strings-follows-pieces
def test_follows_pieces() -> None:
    result = run_pyct(PIECES, '{"s": "q", "t": "r"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert [(fork["line"], fork["expression"]) for fork in forks_of(inputs[0])] == PIECES_FORKS
    # every fork is flipped: some input takes each side of each, and every input the solver
    # handed back took the side it was aimed at, so Python agrees with the solver on each piece
    assert sides_of(inputs) == {
        (line, repr(expression), taken)
        for line, expression in PIECES_FORKS
        for taken in (True, False)
    }
    assert [line["mismatch_at"] for line in inputs[1:]] == [None] * (len(inputs) - 1)
    assert answered_every_fork(result.stdout)
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# follow-strings-changes-the-length
def test_changes_the_length() -> None:
    result = run_pyct(LONG_OR_EMPTY, '{"s": "abc"}')

    assert result.returncode == 0, result.stderr
    solved = [text(line, "s") for line in input_lines(result.stdout)[1:]]
    # the solver lengthens s past the slice's start and shortens it to nothing
    assert any(len(s) > 10 for s in solved), solved
    assert "" in solved


# follow-strings-reports-an-index-past-the-end
def test_reports_an_index_past_the_end() -> None:
    result = run_pyct(INDEX_PAST_THE_END, '{"s": "ab"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    # the index records whether s is long enough before str's own index may raise
    fork = {
        "file": INDEX_PAST_THE_END_FILE,
        "line": 2,
        "col": 7,
        "expression": [">", ["len", "s"], 3],
    }
    assert forks_of(seed) == [{**fork, "taken": False}]
    assert f"fork {INDEX_PAST_THE_END_FILE}:2:7  len(s) > 3  not taken" in (
        result.stderr.splitlines()
    )
    # the detail is CPython's own sentence, so only the kind and the name are pyct's to pin
    failure = seed["failure"]
    assert isinstance(failure, dict), seed
    assert failure["kind"] == "target_raised"
    assert str(failure["detail"]).startswith("IndexError:")
    solved = input_lines(result.stdout)[1]
    assert solved["aim"] == {"file": INDEX_PAST_THE_END_FILE, "line": 2, "col": 7, "position": 0}
    assert len(text(solved, "s")) > 3


# follow-strings-downgrades-a-tracked-index
def test_downgrades_a_tracked_index() -> None:
    result = run_pyct(TRACKED_INDEX, '{"s": "abc", "n": 0}')

    assert result.returncode == 0, result.stderr
    seed = one_line(result.stdout)
    # a tracked int as the index is a form pyct does not encode, so str answers and the
    # operator is named by its dunder
    assert seed["downgrades"] == [{"name": "__getitem__", "count": 1}]
    assert seed["forks"] == []
