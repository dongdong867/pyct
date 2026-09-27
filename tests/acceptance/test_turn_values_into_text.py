"""Acceptance tests for convert-between-ints-and-strings: ints and bools turned into text.

Each test spawns ``python -P -m pyct`` through the harness. A tracked value's `__str__` and
`__format__` hand back a tracked string, which Python passes on whole through `str(...)`,
`format(...)`, an f-string of the value alone, `"{}".format(...)` and `"%s" % ...`, so only a
run through the command line proves the condition reaches the solver.
"""

from tests.acceptance.harness import input_lines, run_pyct
from tests.acceptance.test_bools import expressions, sides
from tests.acceptance.test_ints import argument
from tests.acceptance.test_substitute_conversions import downgrade_names, no_line_lists

TEXT = "targets.strs.text_of_values"


def _ran(function: str, seed: str) -> list[dict[str, object]]:
    result = run_pyct(f"{TEXT}::{function}", seed)
    assert result.returncode == 0, result.stderr
    return input_lines(result.stdout)


# follow-builtins-and-conversions-follows-str-of-an-int
def test_follows_str_of_an_int() -> None:
    inputs = _ran("int_text", '{"n": 0}')

    assert expressions(inputs[0])[0] == ["==", ["str", "n"], "'-42'"]
    solved = inputs[1:]
    assert any(argument(line, "n") == -42 for line in solved)
    assert any(str(argument(line, "n")).startswith("9") for line in solved)
    assert no_line_lists(inputs, "__str__")


# follow-builtins-and-conversions-keeps-str-of-a-tracked-string
def test_keeps_str_of_a_tracked_string() -> None:
    inputs = _ran("kept_text", '{"s": "x"}')

    assert expressions(inputs[0]) == [["==", "s", "'a'"], ["==", "s", "'b'"]]
    assert downgrade_names(inputs[0]) == []


# follow-builtins-and-conversions-follows-str-of-a-bool
def test_follows_str_of_a_bool() -> None:
    inputs = _ran("bool_text", '{"x": 0}')

    expression = ["==", ["str", [">", "x", 0]], "'False'"]
    assert expressions(inputs[0]) == [expression]
    assert sides(inputs, expression) == {True, False}
    assert no_line_lists(inputs, "__str__")


# follow-builtins-and-conversions-follows-an-int-formatted-alone
def test_follows_an_int_formatted_alone() -> None:
    inputs = _ran("formatted_alone", '{"n": 0}')

    wanted = [["==", ["str", "n"], f"'{text}'"] for text in ("7", "8", "9", "10")]
    assert expressions(inputs[0]) == wanted
    assert all(True in sides(inputs, expression) for expression in wanted)
    assert no_line_lists(inputs, "__str__")
    assert no_line_lists(inputs, "__format__")


# follow-builtins-and-conversions-follows-str-through-map
def test_follows_str_through_map() -> None:
    inputs = _ran("mapped", '{"x": 0, "y": 0}')

    expression = ["==", ["+", ["str", "x"], ["str", "y"]], "'12'"]
    assert expressions(inputs[0]) == [expression]
    assert any(f"{argument(line, 'x')}{argument(line, 'y')}" == "12" for line in inputs[1:])


# follow-builtins-and-conversions-leaves-joined-text-plain
def test_leaves_joined_text_plain() -> None:
    inputs = _ran("joined", '{"n": 0}')

    # Python joins the pieces without calling a method of the tracked string, so the first
    # compare is plain Python's False and records nothing
    assert expressions(inputs[0]) == [[">", "n", 3]]
    assert [fork["taken"] for fork in inputs[0]["forks"]] == [False]  # pyrefly: ignore
    assert downgrade_names(inputs[0]) == []


# follow-builtins-and-conversions-downgrades-a-format-spec
def test_downgrades_a_format_spec() -> None:
    inputs = _ran("with_spec", '{"n": 0}')

    assert downgrade_names(inputs[0]) == [("__format__", 1)]
    assert expressions(inputs[0]) == []
