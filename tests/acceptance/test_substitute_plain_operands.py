"""Acceptance tests for substitute-type-name-calls-and-plain-operands: plain operands.

A plain string's method called with a tracked string, and a plain float or bool on the left of
a tracked number, are handed to the tracked value where the code writes them. Each test spawns
``python -P -m pyct`` through the harness, as only a run through the command line substitutes.
"""

from tests.acceptance.harness import REPO_ROOT, first_line, input_lines, run_pyct
from tests.acceptance.test_bools import expressions, failure_of, sides
from tests.acceptance.test_ints import argument, forks_of
from tests.acceptance.test_strs import text
from tests.acceptance.test_substitute_conversions import downgrade_names, forks_taken

INTERCEPT = REPO_ROOT / "targets" / "intercept"
PLAIN_TEXT = "targets.intercept.plain_text"
PLAIN_LEFT = "targets.intercept.plain_left"


def other_sides_taken(inputs: list[dict[str, object]]) -> None:
    """Every fork the seed met is taken both ways, each flip by an input that took its aim."""
    for expression in expressions(inputs[0]):
        assert sides(inputs, expression) == {True, False}, expression
    assert all(line["mismatch_at"] is None for line in inputs[1:]), inputs


# intercept-builtin-functions-follows-search-on-a-plain-string
def test_follows_search_on_a_plain_string() -> None:
    result = run_pyct(f"{PLAIN_TEXT}::search", '{"s": "b"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    written = expressions(inputs[0])
    assert written[0] == ["==", ["find", "'abc'", "s"], 1]
    assert written[-1] == ["==", ["find", "'xyz'", "s"], 0]
    assert len(written) == 6
    other_sides_taken(inputs)


# intercept-builtin-functions-follows-a-plain-float-before-an-int
def test_follows_a_plain_float_before_an_int() -> None:
    result = run_pyct(f"{PLAIN_LEFT}::floats", '{"n": 1}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    compares = [
        [">", ["+", 0.5, "n"], 3.0],
        [">", "n", 2.5],
        [">", ["/", 1.0, "n"], 0.25],
        [">", ["*", 0.5, "n"], 3.0],
    ]
    assert expressions(inputs[0]) == [*compares[:2], ["!=", "n", 0], *compares[2:]]
    for compare in compares:
        assert sides(inputs, compare) == {True, False}, compare
    assert all(isinstance(argument(line, "n"), int) for line in inputs)


# intercept-builtin-functions-follows-a-plain-bool-before-a-tracked-value
def test_follows_a_plain_bool_before_a_tracked_value() -> None:
    result = run_pyct(f"{PLAIN_LEFT}::bools", '{"n": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    written = [[">", ["+", True, "n"], 5], ["==", "n", True], ["&", True, [">", "n", 0]]]
    assert expressions(inputs[0]) == written
    assert f"fork {INTERCEPT / 'plain_left.py'}:19:7  True + n > 5  not taken" in (
        result.stderr.splitlines()
    )
    for expression in written:
        assert sides(inputs, expression) == {True, False}, expression
    assert all(isinstance(argument(line, "n"), int) for line in inputs)
    assert all(line["downgrades"] == [] for line in inputs)


# intercept-builtin-functions-downgrades-an-untaught-form-on-a-plain-string
def test_downgrades_an_untaught_form_on_a_plain_string() -> None:
    result = run_pyct(f"{PLAIN_TEXT}::untaught", '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert downgrade_names(seed) == [("find", 1)]
    assert forks_of(seed) == []


# intercept-builtin-functions-leaves-a-plain-string-call-alone
def test_leaves_a_plain_string_call_alone() -> None:
    result = run_pyct(f"{PLAIN_TEXT}::alone", '{"s": "x"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert expressions(seed) == [["==", "s", "'q'"]]
    assert downgrade_names(seed) == []


# intercept-builtin-functions-finds-the-substring-a-plain-string-lacks
def test_finds_the_substring_a_plain_string_lacks() -> None:
    result = run_pyct(f"{PLAIN_TEXT}::index", '{"s": "b"}')

    assert result.returncode == 0, result.stderr
    seed, second = input_lines(result.stdout)[:2]
    assert [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(seed)] == [
        (33, ["in", "s", "'abc'"], True)
    ]
    assert text(second, "s") not in "abc"
    assert forks_taken(second) == [(["in", "s", "'abc'"], False)]
    failure = failure_of(second)
    assert failure["kind"] == "target_raised"
    assert str(failure["detail"]).startswith("ValueError")
