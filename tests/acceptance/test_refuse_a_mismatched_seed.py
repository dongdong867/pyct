"""Acceptance tests for the refuse-a-mismatched-seed story.

Every test spawns ``python -P -m pyct`` through the harness. A refusal is a
usage error: exit 2, nothing on stdout, and the reason on stderr.
"""

from tests.acceptance.harness import run_pyct

TEXT = "targets.annotations.plain::echo_text"
NUMBER = "targets.annotations.plain::echo_number"
NAME_AND_AGE = "targets.annotations.plain::echo_name_and_age"
TEXT_AND_NUMBER = "targets.annotations.plain::echo_text_and_number"
NUMBERS = "targets.annotations.plain::echo_numbers"
FLAG = "targets.annotations.plain::echo_flag"


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
