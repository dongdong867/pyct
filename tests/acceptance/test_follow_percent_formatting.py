"""Acceptance tests for part B of match-pyct-v1-on-the-measured-functions: `%` formatting.

Each test spawns ``python -P -m pyct`` through the harness: a format is followed only if the
fork on its text reaches the solver and the solver's answer, run by plain Python, takes the
other side.
"""

from collections.abc import Callable

import pytest

from targets.strs import percent_formats
from tests.acceptance.harness import REPO_ROOT, input_lines, run_pyct, summary_line
from tests.acceptance.test_fork_on_a_split_s_count_before_it_unpacks import (
    line_of as line_in,
)
from tests.acceptance.test_fork_on_a_split_s_count_before_it_unpacks import raised_by_python
from tests.acceptance.test_lists import (
    args_of,
    downgrade_names,
    failure_detail,
    fork_line,
    listed,
    solved,
)

FORMATS = "targets.strs.percent_formats"
FORMATS_FILE = str(REPO_ROOT / "targets" / "strs" / "percent_formats.py")


def line_of(text: str, function: str) -> int:
    """The line of the fixture that holds ``text`` inside ``function``."""
    return line_in(text, FORMATS_FILE, after=f"def {function}(")


def run_covers(stdout: str, number: int) -> bool:
    covered = summary_line(stdout)["covered"]
    assert isinstance(covered, dict), stdout
    return number in covered.get(FORMATS_FILE, [])


def covered_by(line: dict[str, object], number: int) -> bool:
    covered = line["covered"]
    assert isinstance(covered, dict), line
    return number in covered.get(FORMATS_FILE, [])


def downgrades_at(line: dict[str, object]) -> list[tuple[object, object]]:
    """Each downgrade of a line as its name and the line it was recorded at."""
    entries = line["downgrades"]
    assert isinstance(entries, list), line
    return [(entry["name"], entry["line"]) for entry in entries]


# match-pyct-v1-on-the-measured-functions-percent-follows-a-tuple
def test_follows_a_tuple() -> None:
    result = run_pyct(f"{FORMATS}::page", '{"title": "x", "body": "y"}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of('if "<script>" in html:', "page")
    formatted = ["%", "'<h1>%s</h1>%s'", ["()", "title", "body"]]
    assert listed(lines[0]) == [(at, ["in", "'<script>'", formatted], False)]
    text = "'<script>' in '<h1>%s</h1>%s' % (title, body)"
    assert fork_line(result.stderr, FORMATS_FILE, at, text, False)
    unsafe = line_of('return "unsafe"', "page")
    assert any(covered_by(line, unsafe) for line in solved(lines)), lines


# match-pyct-v1-on-the-measured-functions-percent-follows-a-literal-format
def test_follows_a_literal_format() -> None:
    result = run_pyct(f"{FORMATS}::count", '{"n": 0}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of('if "%d items" % n == "3 items":', "count")
    assert listed(lines[0]) == [(at, ["==", ["%", "'%d items'", "n"], "'3 items'"], False)]
    assert fork_line(result.stderr, FORMATS_FILE, at, "'%d items' % n == '3 items'", False)
    one = line_of("return 1", "count")
    assert any(args_of(line)["n"] == 3 and covered_by(line, one) for line in solved(lines))


# match-pyct-v1-on-the-measured-functions-percent-follows-an-augmented-format
def test_follows_an_augmented_format() -> None:
    result = run_pyct(f"{FORMATS}::greet", '{"name": "x", "n": 0}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    one = line_of("return 1", "greet")
    assert any(
        args_of(line) == {"name": "bob", "n": 2} and covered_by(line, one) for line in solved(lines)
    ), lines


# match-pyct-v1-on-the-measured-functions-percent-keeps-plain-items-and-percent-signs
def test_keeps_plain_items_and_percent_signs() -> None:
    result = run_pyct(f"{FORMATS}::kept", '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of("if ", "kept")
    formatted = ["%", "'%s-%d%%'", ["()", "s", 7]]
    assert listed(lines[0]) == [(at, ["==", formatted, "'ab-7%'"], False)]
    one = line_of("return 1", "kept")
    assert any(args_of(line)["s"] == "ab" and covered_by(line, one) for line in solved(lines))


# match-pyct-v1-on-the-measured-functions-percent-follows-a-tracked-str-on-the-right
def test_follows_a_tracked_str_on_the_right() -> None:
    result = run_pyct(f"{FORMATS}::on_the_right", '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    one = line_of("return 1", "on_the_right")
    assert any(args_of(line)["s"] == "a" and covered_by(line, one) for line in solved(lines))
    assert not any("__rmod__" in downgrade_names(line) for line in lines), lines


# match-pyct-v1-on-the-measured-functions-percent-downgrades-other-conversions
@pytest.mark.parametrize(
    ("function", "seed", "written"),
    [
        ("padded", '{"s": "a"}', '"%5s" % (s,)'),
        ("in_hex", '{"n": 255}', '"%x" % (n,)'),
        ("quoted", '{"s": "a"}', '"%r" % (s,)'),
        ("keyed", '{"s": "a"}', '"%(k)s" % {"k": s}'),
        ("tracked_format", '{"s": "%d"}', "s % (1,)"),
    ],
)
def test_downgrades_other_conversions(function: str, seed: str, written: str) -> None:
    result = run_pyct(f"{FORMATS}::{function}", seed)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of(written, function)
    # Python's text, plain: the seed's compare records no fork and takes Python's side
    assert listed(lines[0]) == []
    assert downgrades_at(lines[0]) == [("__mod__", at)]
    assert covered_by(lines[0], line_of("return 1", function)), lines[0]


# match-pyct-v1-on-the-measured-functions-percent-leaves-plain-values-as-python
@pytest.mark.parametrize(
    ("function", "call", "forked"),
    [
        ("plain_values", lambda: percent_formats.plain_values(1), True),
        # Python's own TypeError for an int's `%=` with a tuple, before the fork
        ("plain_int_format", lambda: percent_formats.plain_int_format(1), False),
    ],
)
def test_leaves_plain_values_as_python(
    function: str, call: Callable[[], object], *, forked: bool
) -> None:
    result = run_pyct(f"{FORMATS}::{function}", '{"n": 1}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert failure_detail(lines[0]) == raised_by_python(call)
    fork = (line_of("if n > 0:", function), [">", "n", 0], True)
    assert listed(lines[0]) == ([fork] if forked else [])
    assert lines[0]["downgrades"] == []


# match-pyct-v1-on-the-measured-functions-percent-raises-python-s-error
@pytest.mark.parametrize(
    ("function", "call"),
    [
        ("not_a_number", lambda: percent_formats.not_a_number("x")),
        ("too_few", lambda: percent_formats.too_few("x")),
    ],
)
def test_raises_python_s_error(function: str, call: Callable[[], object]) -> None:
    result = run_pyct(f"{FORMATS}::{function}", '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    first = input_lines(result.stdout)[0]
    expected = raised_by_python(call)
    assert expected is not None
    assert failure_detail(first) == expected
    assert run_covers(result.stdout, line_of("return", function))
