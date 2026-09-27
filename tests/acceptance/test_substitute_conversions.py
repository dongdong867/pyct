"""Acceptance tests for substitute-type-name-calls-and-plain-operands: `int`, `float` and `bool`.

Each test spawns ``python -P -m pyct`` through the harness. pyct substitutes a call written
`int(...)`, `float(...)` or `bool(...)`, and `map(int, ...)`, in every module of the target's
top-level package as Python imports it, so only a run through the command line proves it.
"""

import math

from tests.acceptance.harness import REPO_ROOT, first_line, input_lines, run_pyct
from tests.acceptance.test_bools import at, expressions, failure_of, sides
from tests.acceptance.test_floats import reached, real
from tests.acceptance.test_ints import argument, forks_of
from tests.acceptance.test_strs import text

INTERCEPT = REPO_ROOT / "targets" / "intercept"
CONVERSIONS = "targets.intercept.conversions"
CONVERSIONS_FILE = INTERCEPT / "conversions.py"
TEXT_NUMBERS = "targets.intercept.text_numbers"
RAISES = "targets.intercept.conversion_raises"
RAISES_FILE = INTERCEPT / "conversion_raises.py"


def downgrade_names(line: dict[str, object]) -> list[tuple[object, object]]:
    """Each downgrade on a printed line, by its name and count."""
    downgrades = line["downgrades"]
    assert isinstance(downgrades, list), line
    return [(entry["name"], entry["count"]) for entry in downgrades]


def forks_taken(line: dict[str, object]) -> list[tuple[object, object]]:
    """Each fork on a printed line, by its expression and the side it took."""
    return [(fork["expression"], fork["taken"]) for fork in forks_of(line)]


def reads_as_int(value: str) -> int | None:
    """What plain Python reads the text as, or None where it raises."""
    try:
        return int(value)
    except ValueError:
        return None


def reads_as_float(value: str) -> float | None:
    """What plain Python reads the text as, or None where it raises."""
    try:
        return float(value)
    except ValueError:
        return None


def no_line_lists(inputs: list[dict[str, object]], name: str) -> bool:
    return all(name not in [entry for entry, _ in downgrade_names(line)] for line in inputs)


# intercept-builtin-functions-keeps-int-of-a-tracked-int
def test_keeps_int_of_a_tracked_int() -> None:
    result = run_pyct(f"{CONVERSIONS}::int_of_int", '{"x": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert forks_taken(inputs[0]) == [([">", "x", 10], False)]
    assert downgrade_names(inputs[0]) == []
    assert any(argument(line, "x") > 10 for line in inputs[1:])


# intercept-builtin-functions-records-bool-where-it-is-tested
def test_records_bool_where_it_is_tested() -> None:
    result = run_pyct(f"{CONVERSIONS}::bool_where_tested", '{"x": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    seed = inputs[0]
    # the `bool` lines are 9 and 10, the `if y:` and `if z:` lines 12 and 14
    assert at(seed, 9) == [] and at(seed, 10) == []
    assert [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(seed)] == [
        (12, ["!=", "x", 0], False),
        (14, [">", "x", 5], False),
    ]
    assert True in sides(inputs, ["!=", "x", 0])
    assert True in sides(inputs, [">", "x", 5])


# intercept-builtin-functions-follows-int-of-a-string
def test_follows_int_of_a_string() -> None:
    result = run_pyct(f"{CONVERSIONS}::int_of_text", '{"s": "7"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert forks_taken(inputs[0]) == [
        (["isint", "s"], True),
        ([">", ["int", "s"], 100], False),
    ]
    assert downgrade_names(inputs[0]) == []
    lines = result.stderr.splitlines()
    assert f"fork {CONVERSIONS_FILE}:20:8  isint(s)  taken" in lines
    assert f"fork {CONVERSIONS_FILE}:21:7  int(s) > 100  not taken" in lines
    big = [line for line in inputs[1:] if (reads_as_int(text(line, "s")) or 0) > 100]
    assert big, inputs
    assert all(([">", ["int", "s"], 100], True) in forks_taken(line) for line in big)


# intercept-builtin-functions-follows-int-through-map
def test_follows_int_through_map() -> None:
    result = run_pyct(f"{CONVERSIONS}::int_through_map", '{"s": "1", "t": "2"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    summed = ["==", ["+", ["int", "s"], ["int", "t"]], 10]
    assert summed in expressions(inputs[0])
    readings = [(reads_as_int(text(line, "s")), reads_as_int(text(line, "t"))) for line in inputs]
    assert any(s is not None and t is not None and s + t == 10 for s, t in readings), inputs


# intercept-builtin-functions-follows-int-of-a-bool
def test_follows_int_of_a_bool() -> None:
    result = run_pyct(f"{CONVERSIONS}::int_of_bool", '{"x": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    counted = ["==", ["+", ["int", [">", "x", 0]], 1], 2]
    assert expressions(inputs[0]) == [counted]
    assert sides(inputs, counted) == {True, False}
    assert no_line_lists(inputs, "__int__")


# intercept-builtin-functions-follows-int-of-a-float
def test_follows_int_of_a_float() -> None:
    result = run_pyct(f"{CONVERSIONS}::int_of_float", '{"x": 0.5}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert forks_taken(inputs[0]) == [
        (["isfinite", "x"], True),
        (["==", ["int", "x"], 3], False),
    ]
    assert any(3.0 <= real(line, "x") < 4.0 for line in inputs[1:]), inputs
    assert no_line_lists(inputs, "__int__")


# intercept-builtin-functions-follows-float-of-an-int
def test_follows_float_of_an_int() -> None:
    result = run_pyct(f"{CONVERSIONS}::float_of_int", '{"n": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert expressions(inputs[0]) == [[">", ["/", ["float", "n"], 2], 2.5]]
    assert any(argument(line, "n") > 5 for line in inputs[1:]), inputs
    assert no_line_lists(inputs, "__float__")


# intercept-builtin-functions-keeps-float-of-a-tracked-float
def test_keeps_float_of_a_tracked_float() -> None:
    result = run_pyct(f"{CONVERSIONS}::float_of_float", '{"x": 0.0}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert expressions(seed) == [[">", "x", 2.5]]
    assert downgrade_names(seed) == []


# intercept-builtin-functions-follows-float-of-a-bool
def test_follows_float_of_a_bool() -> None:
    result = run_pyct(f"{CONVERSIONS}::float_of_bool", '{"x": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    scaled = [">", ["*", ["float", [">", "x", 0]], 2.5], 1.0]
    assert expressions(inputs[0]) == [scaled]
    assert any(
        argument(line, "x") > 0 and (scaled, True) in forks_taken(line) for line in inputs[1:]
    )
    assert no_line_lists(inputs, "__float__")


# intercept-builtin-functions-follows-float-of-a-string
def test_follows_float_of_a_string() -> None:
    result = run_pyct(f"{CONVERSIONS}::float_of_text", '{"s": "0"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    above = [">", ["float", "s"], 2.5]
    assert forks_taken(inputs[0]) == [(["isfloat", "s"], True), (above, False)]
    big = [line for line in inputs[1:] if (reads_as_float(text(line, "s")) or 0.0) > 2.5]
    assert big, inputs
    assert all(line["mismatch_at"] is None for line in big)


# intercept-builtin-functions-reads-int-text-as-python-does
def test_reads_int_text_as_python_does() -> None:
    result = run_pyct(f"{TEXT_NUMBERS}::thousand", '{"s": "0"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    thousand = [line for line in inputs[1:] if reads_as_int(text(line, "s")) == 1000]
    assert thousand, inputs
    assert all(line["mismatch_at"] is None for line in thousand)

    spaced = run_pyct(f"{TEXT_NUMBERS}::thousand", '{"s": " -1_0 "}')

    assert spaced.returncode == 0, spaced.stderr
    assert forks_taken(first_line(spaced.stdout)) == [
        (["isint", "s"], True),
        (["==", ["int", "s"], 1000], False),
    ]


# intercept-builtin-functions-downgrades-int-with-a-base
def test_downgrades_int_with_a_base() -> None:
    result = run_pyct(f"{TEXT_NUMBERS}::with_a_base", '{"s": "ff"}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert downgrade_names(seed) == [("int", 1)]
    assert forks_of(seed) == []


# intercept-builtin-functions-keeps-a-non-ascii-digit-honest
def test_keeps_a_non_ascii_digit_honest() -> None:
    result = run_pyct(f"{TEXT_NUMBERS}::twelve", '{"s": "١٢"}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert (["==", ["int", "s"], 12], True) in forks_taken(inputs[0])
    solved = [line for line in result.stderr.splitlines() if line.startswith("solver {")]
    ends = [
        line
        for line in result.stderr.splitlines()
        if line == "reached" or line.startswith("left the plan")
    ]
    assert len(ends) == len(solved) == len(inputs) - 1


# intercept-builtin-functions-reads-float-text-as-python-does
def test_reads_float_text_as_python_does() -> None:
    result = run_pyct(f"{TEXT_NUMBERS}::read_as_float", '{"s": "1"}')

    assert result.returncode == 0, result.stderr
    solved = [line for line in input_lines(result.stdout)[1:] if line["mismatch_at"] is None]
    readings = [reads_as_float(text(line, "s")) for line in solved]
    assert any(reading is not None and math.isnan(reading) for reading in readings), solved
    assert 100000.0 in readings, solved


# intercept-builtin-functions-reports-a-slow-conversion-as-a-miss
def test_reports_a_slow_conversion_as_a_miss() -> None:
    result = run_pyct(f"{CONVERSIONS}::float_of_text", "--solver-timeout", "0.001", '{"s": "0"}')

    assert result.returncode == 0, result.stderr
    site = f"missed {CONVERSIONS_FILE}:66:7 "
    missed = [line.removeprefix(site) for line in result.stderr.splitlines() if site in line]
    assert missed, result.stderr
    assert all(why in ("timeout", "unknown") for why in missed)
    above = [">", ["float", "s"], 2.5]
    solved = input_lines(result.stdout)[1:]
    assert all((above, True) not in forks_taken(line) for line in solved)


# intercept-builtin-functions-keeps-a-module-s-own-type-name
def test_keeps_a_module_s_own_type_name() -> None:
    result = run_pyct("targets.intercept.own_int::convert", '{"x": 0}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    # the module's own `int` answers 7, so `int(x) > 3` holds, as plain Python has it
    assert seed["covered"] == {str(INTERCEPT / "own_int.py"): [2, 6, 7]}
    assert forks_of(seed) == []
    assert downgrade_names(seed) == []


# intercept-builtin-functions-names-the-loss-through-an-alias
def test_names_the_loss_through_an_alias() -> None:
    result = run_pyct(f"{CONVERSIONS}::aliased", '{"x": 0}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert downgrade_names(seed) == [("__int__", 1)]
    assert forks_of(seed) == []


# intercept-builtin-functions-leaves-a-conversion-raise-to-the-target
def test_leaves_a_conversion_raise_to_the_target() -> None:
    result = run_pyct(f"{RAISES}::of_box", '{"x": 0}')

    assert result.returncode == 0, result.stderr
    failure = failure_of(first_line(result.stdout))
    assert failure["kind"] == "target_raised"
    assert str(failure["detail"]).startswith("ZeroDivisionError")


def raised(line: dict[str, object]) -> str:
    """The name of what the target raised, off a printed line."""
    failure = failure_of(line)
    assert failure["kind"] == "target_raised", line
    return str(failure["detail"]).split(":", 1)[0]


# intercept-builtin-functions-finds-the-string-int-refuses
def test_finds_the_string_int_refuses() -> None:
    result = run_pyct(f"{RAISES}::int_of", '{"s": "12"}')

    assert result.returncode == 0, result.stderr
    seed, second = input_lines(result.stdout)[:2]
    assert [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(seed)] == [
        (11, ["isint", "s"], True)
    ]
    assert reads_as_int(text(second, "s")) is None
    assert forks_taken(second) == [(["isint", "s"], False)]
    assert raised(second) == "ValueError"


# intercept-builtin-functions-finds-the-float-int-cannot-convert
def test_finds_the_float_int_cannot_convert() -> None:
    result = run_pyct(f"{RAISES}::int_of_float", '{"x": 2.5}')

    assert result.returncode == 0, result.stderr
    seed, second = input_lines(result.stdout)[:2]
    assert [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(seed)] == [
        (15, ["isfinite", "x"], True)
    ]
    assert not math.isfinite(real(second, "x"))
    assert raised(second) in ("ValueError", "OverflowError")


# intercept-builtin-functions-finds-the-string-float-refuses
def test_finds_the_string_float_refuses() -> None:
    result = run_pyct(f"{RAISES}::float_of", '{"s": "1.5"}')

    assert result.returncode == 0, result.stderr
    seed, second = input_lines(result.stdout)[:2]
    assert [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(seed)] == [
        (19, ["isfloat", "s"], True)
    ]
    assert reads_as_float(text(second, "s")) is None
    assert raised(second) == "ValueError"
    assert reached(input_lines(result.stdout))
