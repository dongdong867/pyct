"""Acceptance tests for the follow-positions-into-a-string story.

Each test spawns ``python -P -m pyct`` through the harness, as the other string tests do: a
position is followed only if the fork built on it reaches the solver and the solver's answer
runs, so only a real run through the command line proves it. Where a criterion says Python
agrees, the test works the target's condition out in Python on the input the solver handed
back.
"""

from collections.abc import Callable

from tests.acceptance.harness import (
    REPO_ROOT,
    first_line,
    input_lines,
    run_pyct,
    summary_line,
)
from tests.acceptance.test_str_pieces import sides_of
from tests.acceptance.test_strs import forks_of, number, text

FOUND_KEY = "targets.strs.found_key::key_of"
TRACKED_INDEX = "targets.strs.tracked_index::pick"
TRACKED_INDEX_FILE = str(REPO_ROOT / "targets" / "strs" / "tracked_index.py")
INDEX_OUT_OF_RANGE = "targets.strs.index_out_of_range::pick"
SEARCH_FROM_POSITION = "targets.strs.search_from_position::hits"
PREFIXES = "targets.strs.prefixes::route"
PREFIXES_FILE = str(REPO_ROOT / "targets" / "strs" / "prefixes.py")
ONE_REPLACEMENT = "targets.strs.one_replacement::swap"
REVERSED_TEXT = "targets.strs.reversed_text::mirror"
REVERSED_TEXT_FILE = str(REPO_ROOT / "targets" / "strs" / "reversed_text.py")
NEGATIVE_POSITION = "targets.strs.negative_position::tail"
EMPTY_NEEDLE = "targets.strs.empty_needle::past"
REPLACE_ONCE = "targets.strs.replace_once::mark"
REVERSED_BETWEEN = "targets.strs.reversed_between::back"
OTHER_FORMS = "targets.strs.other_forms::other"
INDEX_FROM_POSITION = "targets.strs.index_from_position::f"

# the two forks a tracked index records before str's own index may raise
LONG_ENOUGH: list[object] = [">", ["len", "s"], "n"]
NOT_TOO_SHORT: list[object] = [">=", ["len", "s"], ["-", "n"]]


def no_downgrade(stdout: str) -> bool:
    """Whether no input's line lists a downgrade."""
    return all(line["downgrades"] == [] for line in input_lines(stdout))


def solved(stdout: str) -> list[dict[str, object]]:
    """The solver's lines, each checked to have followed the plan it was handed."""
    lines = input_lines(stdout)[1:]
    assert [line["mismatch_at"] for line in lines] == [None] * len(lines), stdout
    return lines


def flipped_every_fork(stdout: str) -> bool:
    """Whether some input took each side of every fork any input took, and every solver input
    took the side it was aimed at, which is Python agreeing with the solver on each."""
    lines = input_lines(stdout)
    sides = sides_of(lines)
    solved(stdout)
    return all((at, written, not taken) in sides for at, written, taken in sides)


def any_line(stdout: str, holds: Callable[[dict[str, object]], bool]) -> bool:
    """Whether Python finds the condition true on some solver input."""
    return any(holds(line) for line in solved(stdout))


def aimed_at(line: dict[str, object]) -> object:
    """The position on the path of the fork a solver input was aimed at."""
    aim = line["aim"]
    assert isinstance(aim, dict), line
    return aim["position"]


def failure_of(line: dict[str, object]) -> str:
    """The kind and the first word of a line's failure: `target_raised IndexError:`."""
    failure = line["failure"]
    assert isinstance(failure, dict), line
    return f"{failure['kind']} {str(failure['detail']).split()[0]}"


# follow-positions-into-a-string-slices-at-a-found-position
def test_slices_at_a_found_position() -> None:
    result = run_pyct(FOUND_KEY, '{"s": "host=a"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    key: list[object] = ["[:]", "s", None, ["find", "s", "'='"]]
    assert [fork["expression"] for fork in forks_of(seed)] == [["==", key, "'port'"]]
    assert any_line(result.stdout, lambda line: (s := text(line, "s"))[: s.find("=")] == "port")
    assert no_downgrade(result.stdout)


# follow-positions-into-a-string-follows-a-tracked-index
def test_follows_a_tracked_index() -> None:
    result = run_pyct(TRACKED_INDEX, '{"s": "abc", "n": 0}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert [(f["line"], f["expression"], f["taken"]) for f in forks_of(seed)] == [
        (2, LONG_ENOUGH, True),
        (2, NOT_TOO_SHORT, True),
        (2, ["==", ["[]", "s", "n"], "'z'"], False),
    ]
    assert f"fork {TRACKED_INDEX_FILE}:2:7  len(s) > n  taken" in result.stderr.splitlines()
    assert no_downgrade(result.stdout)
    assert any_line(result.stdout, lambda line: text(line, "s")[number(line, "n")] == "z")


# follow-positions-into-a-string-follows-a-search-from-a-tracked-position
def test_follows_a_search_from_a_tracked_position() -> None:
    result = run_pyct(SEARCH_FROM_POSITION, '{"s": "abc", "n": 0}')

    assert result.returncode == 0, result.stderr
    compares = forks_of(first_line(result.stdout))
    assert [fork["line"] for fork in compares] == [3, 5, 7, 9, 11, 13]
    assert compares[0]["expression"] == ["==", ["find", "s", "'x'", "n"], 3]
    assert compares[-1]["expression"] == [">=", ["find", "s", "'y'", None, "n"], 0]
    assert flipped_every_fork(result.stdout)
    assert no_downgrade(result.stdout)


# follow-positions-into-a-string-follows-a-tuple-of-prefixes
def test_follows_a_tuple_of_prefixes() -> None:
    result = run_pyct(PREFIXES, '{"s": "x", "t": "q"}')

    assert result.returncode == 0, result.stderr
    expressions = {repr(fork["expression"]) for fork in forks_of(first_line(result.stdout))}
    assert expressions == {
        repr(["startswith", "s", ["()", "'GET'", "'POST'"]]),
        repr(["endswith", "s", ["()", "'.py'", "t"]]),
    }
    assert flipped_every_fork(result.stdout)
    line = f"fork {PREFIXES_FILE}:2:7  s.startswith(('GET', 'POST'))  not taken"
    assert line in result.stderr.splitlines()


# follow-positions-into-a-string-follows-one-replacement
def test_follows_one_replacement() -> None:
    result = run_pyct(ONE_REPLACEMENT, '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    expression = ["==", ["replace", "s", "'a'", "'b'", 1], "'bab'"]
    assert [fork["expression"] for fork in forks_of(seed)] == [expression]
    assert any_line(result.stdout, lambda line: text(line, "s").replace("a", "b", 1) == "bab")
    assert no_downgrade(result.stdout)


# follow-positions-into-a-string-follows-a-reversed-string
def test_follows_a_reversed_string() -> None:
    result = run_pyct(REVERSED_TEXT, '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    expression = ["==", ["[:]", "s", None, None, -1], "'abc'"]
    assert [fork["expression"] for fork in forks_of(seed)] == [expression]
    assert any_line(result.stdout, lambda line: text(line, "s") == "cba")
    line = f"fork {REVERSED_TEXT_FILE}:2:7  s[::-1] == 'abc'  not taken"
    assert line in result.stderr.splitlines()


# follow-positions-into-a-string-counts-a-negative-position-from-the-end
def test_counts_a_negative_position_from_the_end() -> None:
    result = run_pyct(NEGATIVE_POSITION, '{"s": "abc", "n": -1}')

    assert result.returncode == 0, result.stderr
    assert len(forks_of(first_line(result.stdout))) == 4
    assert flipped_every_fork(result.stdout)


# follow-positions-into-a-string-reads-an-empty-needle-past-the-end-as-python-does
def test_reads_an_empty_needle_past_the_end_as_python_does() -> None:
    result = run_pyct(EMPTY_NEEDLE, '{"s": "abc", "n": 0}')

    assert result.returncode == 0, result.stderr
    assert any_line(result.stdout, lambda line: number(line, "n") > len(text(line, "s")))
    assert flipped_every_fork(result.stdout)


# follow-positions-into-a-string-replaces-an-empty-or-tracked-old-string-once
def test_replaces_an_empty_or_tracked_old_string_once() -> None:
    result = run_pyct(REPLACE_ONCE, '{"s": "q", "t": "q"}')

    assert result.returncode == 0, result.stderr
    assert len(forks_of(first_line(result.stdout))) == 2
    assert flipped_every_fork(result.stdout)
    assert no_downgrade(result.stdout)


# follow-positions-into-a-string-follows-a-step-of-minus-one-between-bounds
def test_follows_a_step_of_minus_one_between_bounds() -> None:
    result = run_pyct(REVERSED_BETWEEN, '{"s": "abcd", "n": 0}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    expression = ["==", ["[:]", "s", "n", 0, -1], "'cb'"]
    assert [(fork["expression"], fork["taken"]) for fork in forks_of(seed)] == [(expression, False)]
    assert any_line(result.stdout, lambda line: text(line, "s")[number(line, "n") : 0 : -1] == "cb")


# follow-positions-into-a-string-keeps-the-other-forms-downgrades
def test_keeps_the_other_forms_downgrades() -> None:
    result = run_pyct(OTHER_FORMS, '{"s": "abc", "k": 1}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    downgrades = seed["downgrades"]
    assert isinstance(downgrades, list), seed
    assert [(entry["name"], entry["count"]) for entry in downgrades] == [
        ("__getitem__", 1),
        ("replace", 1),
        ("__getitem__", 1),
        ("replace", 1),
    ]
    assert seed["forks"] == []


# follow-positions-into-a-string-reports-a-tracked-index-past-the-end
def test_reports_a_tracked_index_past_the_end() -> None:
    result = run_pyct(INDEX_OUT_OF_RANGE, '{"s": "ab", "n": 5}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert [(f["line"], f["expression"], f["taken"]) for f in forks_of(seed)] == [
        (2, LONG_ENOUGH, False)
    ]
    assert failure_of(seed) == "target_raised IndexError:"
    # flipping the fork asks only that n < len(s), which a negative n past the start also
    # meets, so the input aimed at it takes it and may still raise at the second fork. The
    # flip of that one hands back an input that raises nothing
    lines = solved(result.stdout)
    aimed = [line for line in lines if aimed_at(line) == 0]
    assert aimed and all(forks_of(line)[0]["taken"] is True for line in aimed)
    assert any(line["failure"] is None for line in lines)


# follow-positions-into-a-string-reports-a-tracked-index-before-the-start
def test_reports_a_tracked_index_before_the_start() -> None:
    result = run_pyct(INDEX_OUT_OF_RANGE, '{"s": "ab", "n": -5}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert [(f["line"], f["expression"], f["taken"]) for f in forks_of(seed)] == [
        (2, LONG_ENOUGH, True),
        (2, NOT_TOO_SHORT, False),
    ]
    assert failure_of(seed) == "target_raised IndexError:"
    aimed = [line for line in solved(result.stdout) if aimed_at(line) == 1]
    assert aimed and all(line["failure"] is None for line in aimed)


# follow-positions-into-a-string-reports-a-search-from-a-position-that-finds-nothing
def test_reports_a_search_from_a_position_that_finds_nothing() -> None:
    result = run_pyct(INDEX_FROM_POSITION, '{"s": "axb", "n": 0}')

    assert result.returncode == 0, result.stderr
    seed, second = input_lines(result.stdout)[:2]
    found: list[object] = ["!=", ["find", "s", "'x'", "n"], -1]
    assert [(f["line"], f["expression"], f["taken"]) for f in forks_of(seed)] == [(2, found, True)]
    assert aimed_at(second) == 0
    assert text(second, "s").find("x", number(second, "n")) == -1
    assert [(f["expression"], f["taken"]) for f in forks_of(second)] == [(found, False)]
    assert failure_of(second) == "target_raised ValueError:"
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"
