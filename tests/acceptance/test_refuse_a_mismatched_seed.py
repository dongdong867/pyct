"""Acceptance tests for the refuse-a-mismatched-seed story.

Every test spawns ``python -P -m pyct`` through the harness. A refusal is a
usage error: exit 2, nothing on stdout, and the reason on stderr.
"""

from tests.acceptance.harness import first_line, run_pyct

TEXT = "targets.annotations.plain::echo_text"
NUMBER = "targets.annotations.plain::echo_number"
NAME_AND_AGE = "targets.annotations.plain::echo_name_and_age"
TEXT_AND_NUMBER = "targets.annotations.plain::echo_text_and_number"
NUMBERS = "targets.annotations.plain::echo_numbers"
FLAG = "targets.annotations.plain::echo_flag"
STORED_AS_TEXT = "targets.annotations.stored_as_text::echo_text"
NOT_PLAIN = "targets.annotations.not_plain::echo_both"
BARE = "targets.annotations.bare::echo"
UNRESOLVED = "targets.annotations.unresolved::echo_text"


# refuses-a-number-for-a-str
def test_refuses_a_number_for_a_str() -> None:
    result = run_pyct(TEXT, '{"s": 5}')

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert "s" in result.stderr
    assert "str" in result.stderr
    assert "5" in result.stderr


# refuses-text-for-an-int
def test_refuses_text_for_an_int() -> None:
    result = run_pyct(NUMBER, '{"n": "5"}')

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert "n" in result.stderr
    assert "int" in result.stderr
    # the value is spelled the way it was typed, so the quotes stay on
    assert '"5"' in result.stderr


# reports-every-contradiction-at-once
def test_reports_every_contradiction_at_once() -> None:
    result = run_pyct(NAME_AND_AGE, '{"name": 5, "age": "x"}')

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    lines = result.stderr.splitlines()
    assert [line for line in lines if line.startswith("name ")] == ["name must be a str, got 5"]
    assert [line for line in lines if line.startswith("age ")] == ['age must be an int, got "x"']


# runs-a-seed-that-matches
def test_runs_a_seed_that_matches() -> None:
    result = run_pyct(TEXT_AND_NUMBER, '{"s": "abc", "n": 1}')

    assert result.returncode == 0, result.stderr
    assert first_line(result.stdout)["args"] == {"s": "abc", "n": 1}


# follows-python-on-numbers
def test_follows_python_on_numbers() -> None:
    # a bool is an int to Python, and an int stands in where a float is asked for
    result = run_pyct(NUMBERS, '{"n": true, "x": 3, "y": false}')

    assert result.returncode == 0, result.stderr
    assert first_line(result.stdout)["args"] == {"n": True, "x": 3, "y": False}


# refuses-an-int-for-a-bool
def test_refuses_an_int_for_a_bool() -> None:
    result = run_pyct(FLAG, '{"b": 1}')

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert "b must be a bool, got 1" in result.stderr


# refuses-none-for-a-plain-type
def test_refuses_none_for_a_plain_type() -> None:
    result = run_pyct(TEXT, '{"s": null}')

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert "s must be a str, got null" in result.stderr


# checks-an-annotation-stored-as-text
def test_checks_an_annotation_stored_as_text() -> None:
    result = run_pyct(STORED_AS_TEXT, '{"s": 5}')

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    assert "s must be a str, got 5" in result.stderr


# skips-an-annotation-that-is-not-plain
def test_skips_an_annotation_that_is_not_plain() -> None:
    result = run_pyct(NOT_PLAIN, '{"s": 5, "xs": "x"}')

    assert result.returncode == 0, result.stderr
    assert first_line(result.stdout)["args"] == {"s": 5, "xs": "x"}


# skips-a-parameter-with-no-annotation
def test_skips_a_parameter_with_no_annotation() -> None:
    result = run_pyct(BARE, '{"s": 5}')

    assert result.returncode == 0, result.stderr
    assert first_line(result.stdout)["args"] == {"s": 5}


# skips-an-annotation-that-cannot-be-resolved
def test_skips_an_annotation_that_cannot_be_resolved() -> None:
    result = run_pyct(UNRESOLVED, '{"s": 5}')

    assert result.returncode == 0, result.stderr
    assert first_line(result.stdout)["args"] == {"s": 5}
