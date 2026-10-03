"""Acceptance tests for the follow-string-pieces child of the follow-strings story.

Each test spawns ``python -P -m pyct`` through the harness, as the other string tests do: a
piece is followed only if the fork built on it reaches the solver and the solver's answer
runs, so only a real run through the command line proves it.
"""

from tests.acceptance.harness import (
    REPO_ROOT,
    first_line,
    forks_of,
    input_lines,
    run_pyct,
    summary_line,
)
from tests.acceptance.test_strs import text

INDEX_AND_SLICE = "targets.strs.index_and_slice::shape"
# each fork the seed takes in ``shape``, in order: the line, the expression, and the side. An
# index adds its long-enough fork on the line of the compare it feeds; a slice adds none. The
# target catches each index's IndexError, so an empty s goes on to every later fork
INDEX_AND_SLICE_FORKS: list[tuple[int, list[object], bool]] = [
    (3, [">", ["len", "s"], 0], True),
    (3, ["==", ["[]", "s", 0], "'a'"], False),
    (8, [">=", ["len", "s"], 1], True),
    (8, ["==", ["[]", "s", -1], "'z'"], False),
    (12, ["==", ["[:]", "s", 1, 3], "'bc'"], False),
    (14, ["==", ["[:]", "s", 2, None], "'cd'"], False),
    (16, ["==", ["[:]", "s", None, -1], "'xy'"], False),
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
REBUILT = "targets.strs.rebuilt::rebuild"
REBUILT_FILE = str(REPO_ROOT / "targets" / "strs" / "rebuilt.py")
PADDED = "targets.strs.padded::pad"


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
    # handed back took the side it was aimed at
    assert sides_of(inputs) == {
        (line, repr(expression), taken)
        for line, expression, _ in INDEX_AND_SLICE_FORKS
        for taken in (True, False)
    }
    assert [line["mismatch_at"] for line in inputs[1:]] == [None] * (len(inputs) - 1)
    assert answered_every_fork(result.stdout)
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


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


def printed_nodes(expression: object) -> int:
    """Nodes of an expression as a line prints it: a list and each of its operands.

    Counted on a stack of its own, since a printed expression may nest deeper than Python
    recurses.
    """
    nodes, stack = 0, [expression]
    while stack:
        part = stack.pop()
        nodes += 1
        if isinstance(part, list):
            stack.extend(part[1:])
    return nodes


def cut_counts(expression: object) -> list[int]:
    """The N of every cut part `["...", N]` in a printed expression, left to right."""
    if not isinstance(expression, list):
        return []
    if expression[0] == "...":
        return [expression[1]]
    return [count for part in expression[1:] for count in cut_counts(part)]


# follow-strings-cuts-a-long-expression
def test_cuts_a_long_expression() -> None:
    # the criterion names no budget, and a range over the length is followed, so the solver can
    # always lengthen the loop and the tree never empties: a budget ends the run
    result = run_pyct(REBUILT, '{"s": "aaaaaaaaaaaaaaaaaa"}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    forks = [fork for line in inputs for fork in forks_of(line)]
    # each pass holds the last one three times, so written out the expression triples every pass
    assert all(printed_nodes(fork["expression"]) <= 1000 for fork in forks)
    seed_forks = forks_of(inputs[0])
    cut = seed_forks[-1]
    counts = cut_counts(cut["expression"])
    assert counts and all(isinstance(count, int) and count > 2 for count in counts)
    site = f"{REBUILT_FILE}:{cut['line']}:{cut['col']}"
    fork_line = next(line for line in result.stderr.splitlines() if line.startswith(f"fork {site}"))
    assert fork_line.count(" nodes)") == len(counts)
    assert all(f"...({count} nodes)" in fork_line for count in counts)
    # the solver still gets the whole condition, so the cut fork is flipped like any other
    position = len(seed_forks) - 1
    aim = {"file": REBUILT_FILE, "line": cut["line"], "col": cut["col"], "position": position}
    reaching = [line for line in inputs[1:] if line["aim"] == aim and line["mismatch_at"] is None]
    assert reaching, [line["aim"] for line in inputs[1:]]
    assert text(reaching[0], "s") == "abcdefghijklmnopqr"


# follow-strings-cuts-a-long-expression
def test_cuts_a_string_built_over_five_thousand_passes() -> None:
    result = run_pyct(PADDED, '{"s": "a"}')

    # the string nests five thousand operations deep, far past Python's recursion limit, and
    # the line, the fork line and the solver each walk it
    assert result.returncode == 0, result.stderr
    seed, solved = input_lines(result.stdout)
    assert all(printed_nodes(fork["expression"]) <= 1000 for fork in forks_of(seed))
    assert " nodes).startswith('ok')" not in result.stderr
    assert " + ' ').startswith('ok')  not taken" in result.stderr
    assert text(solved, "s").startswith("ok")
    assert solved["mismatch_at"] is None
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"
