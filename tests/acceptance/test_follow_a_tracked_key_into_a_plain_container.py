"""Acceptance tests for follow-a-tracked-key-into-a-plain-container.

A tracked str, int, bool or float key into a plain dict, list, tuple or str forks on which entry
the lookup finds, so the solver tries each key the container holds and the value found stays
connected to the input. Each test runs pyct through the command line and reads the printed
lines against the same call in plain Python.
"""

from pathlib import Path

import pytest

from targets.dicts import plain_lookups
from targets.lists import plain_lookups as list_lookups
from targets.strs import plain_lookups as str_lookups
from tests.acceptance.harness import REPO_ROOT, downgrade, first_line, input_lines, run_pyct
from tests.acceptance.test_bool_parameters import covered
from tests.acceptance.test_follow_an_int_subclass_on_the_left import placed
from tests.acceptance.test_lists import failure_detail
from tests.acceptance.test_write_an_int_subclass_operand_as_a_plain_int import solver_lines

DICTS = "targets.dicts.plain_lookups"
DICTS_FILE = REPO_ROOT / "targets" / "dicts" / "plain_lookups.py"
LISTS = "targets.lists.plain_lookups"
LISTS_FILE = REPO_ROOT / "targets" / "lists" / "plain_lookups.py"
STRS = "targets.strs.plain_lookups"
STRS_FILE = REPO_ROOT / "targets" / "strs" / "plain_lookups.py"


def line_of(function: str, text: str, file: Path = DICTS_FILE) -> int:
    """The line of the fixture's ``function`` that holds ``text``, counted from 1."""
    lines = file.read_text().splitlines()
    start = next(n for n, line in enumerate(lines) if line.startswith(f"def {function}("))
    return next(n for n, line in enumerate(lines[start:], start + 1) if text in line)


def returns_of(function: str, file: Path = DICTS_FILE) -> list[int]:
    """The lines of the fixture's ``function`` that hold a `return`."""
    lines = file.read_text().splitlines()
    start = next(n for n, line in enumerate(lines) if line.startswith(f"def {function}("))
    end = next((n for n, line in enumerate(lines[start:], start) if line == ""), len(lines))
    return [n for n in range(start + 1, end + 1) if "return " in lines[n - 1]]


def check_every_return_is_covered(function: str, stdout: str, file: Path = DICTS_FILE) -> None:
    """Every `return` of the function is covered by some input."""
    reached = {number for line in input_lines(stdout) for number in covered(line, str(file))}
    assert set(returns_of(function, file)) <= reached, (sorted(reached), stdout)


def keys_tried(stdout: str, name: str = "s") -> set[object]:
    """The argument `name` each of the solver's inputs hands the function."""
    return {line["args"][name] for line in solver_lines(stdout)}  # type: ignore[index]


# follow-a-tracked-key-into-a-plain-container-run-plain-lookup-tries-each-key
def test_a_plain_dict_s_get_tries_each_key() -> None:
    result = run_pyct(f"{DICTS}::found", '{"s": "US"}', "--goal", "bugs")

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert plain_lookups.found("US") == "us"
    at = line_of("found", "METAS.get(s)")
    assert placed(seed, at) == [(["==", "s", "'US'"], True)]
    assert seed["downgrades"] == []
    check_every_return_is_covered("found", result.stdout)
    assert {"FR", "DE"} <= keys_tried(result.stdout)


# follow-a-tracked-key-into-a-plain-container-run-plain-lookup-tries-each-key
def test_a_plain_dict_s_subscript_in_a_try_tries_each_key() -> None:
    result = run_pyct(f"{DICTS}::guarded", '{"s": "US"}', "--goal", "bugs")

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert plain_lookups.guarded("US") == "us"
    assert placed(seed, line_of("guarded", "METAS[s]")) == [(["==", "s", "'US'"], True)]
    check_every_return_is_covered("guarded", result.stdout)
    assert {"FR", "DE"} <= keys_tried(result.stdout)


# follow-a-tracked-key-into-a-plain-container-run-plain-lookup-miss
@pytest.mark.parametrize("function", ["found", "guarded", "defaulted", "raised"])
def test_a_miss_records_one_fork_per_key_and_answers_as_python_does(function: str) -> None:
    result = run_pyct(f"{DICTS}::{function}", '{"s": "XX"}', "--goal", "bugs")

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    at = line_of(function, "METAS")
    assert placed(seed, at) == [(["==", "s", f"'{key}'"], False) for key in plain_lookups.METAS]
    if function == "raised":
        with pytest.raises(KeyError) as plain:
            plain_lookups.raised("XX")
        assert failure_detail(seed) == f"KeyError: {plain.value}"
    else:
        assert failure_detail(seed) is None
        assert getattr(plain_lookups, function)("XX") in ("none", 7)


# follow-a-tracked-key-into-a-plain-container-run-plain-lookup-list-item
def test_a_tracked_int_picks_each_item_of_a_plain_list() -> None:
    result = run_pyct(f"{LISTS}::picked", '{"n": 0}', "--goal", "bugs")

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert list_lookups.picked(0) == 0
    at = line_of("picked", "CODES[n]", LISTS_FILE)
    assert placed(seed, at) == [([">=", "n", 0], True), (["==", "n", 0], True)]
    check_every_return_is_covered("picked", result.stdout, LISTS_FILE)
    assert {1, 2, 3} <= keys_tried(result.stdout, "n")


# follow-a-tracked-key-into-a-plain-container-run-plain-lookup-list-item
def test_an_input_past_either_end_raises_index_error() -> None:
    result = run_pyct(f"{LISTS}::picked", '{"n": 0}', "--goal", "bugs")

    assert result.returncode == 0, result.stderr
    size = len(list_lookups.CODES)
    with pytest.raises(IndexError) as plain:
        list_lookups.CODES[size]
    raised = {
        line["args"]["n"]: failure_detail(line)  # type: ignore[index]
        for line in solver_lines(result.stdout)
        if failure_detail(line) is not None
    }
    assert any(n >= size for n in raised) and any(n < -size for n in raised), raised  # type: ignore[operator]
    assert set(raised.values()) == {f"IndexError: {plain.value}"}


# follow-a-tracked-key-into-a-plain-container-run-plain-lookup-str-char
def test_a_tracked_int_into_a_plain_str_gives_a_tracked_character() -> None:
    result = run_pyct(f"{STRS}::lettered", '{"n": 0}', "--goal", "bugs")

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert str_lookups.lettered(0) == 0
    at = line_of("lettered", "ALPHA[n]", STRS_FILE)
    alpha = f"'{str_lookups.ALPHA}'"
    assert placed(seed, at) == [
        ([">", ["len", alpha], "n"], True),
        ([">=", ["len", alpha], ["-", "n"]], True),
        (["==", ["[]", alpha, "n"], "'q'"], False),
    ]
    check_every_return_is_covered("lettered", result.stdout, STRS_FILE)
    assert 16 in keys_tried(result.stdout, "n")


# follow-a-tracked-key-into-a-plain-container-run-plain-lookup-past-limit
def test_a_dict_past_the_limit_is_python_s_own_and_names_get() -> None:
    result = run_pyct(f"{DICTS}::past_limit", '{"s": "k0"}', "--goal", "bugs")

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert plain_lookups.past_limit("k0") == "other"
    at = line_of("past_limit", "LARGE.get(s)")
    assert placed(seed, at) == [(["==", "s", "'k0'"], True)]
    column = DICTS_FILE.read_text().splitlines()[at - 1].index("LARGE")
    assert seed["downgrades"] == [
        downgrade("get", 1, f"targets/dicts/plain_lookups.py:{at}:{column}")
    ]
