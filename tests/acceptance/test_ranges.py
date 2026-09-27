"""Acceptance tests for the follow-ranges child of the follow-loops-and-ranges story.

Each test spawns ``python -P -m pyct`` through the harness: pyct substitutes a call written
`range(...)` in the target's package as Python imports it, and a range's forks only count once
they reach the tree and the solver's answers run, so only a real run through the command line
proves it.
"""

from tests.acceptance.harness import (
    REPO_ROOT,
    downgrade,
    first_line,
    input_lines,
    run_pyct,
    summary_line,
)
from tests.acceptance.test_loops import covers
from tests.acceptance.test_strs import forks_of, number, text
from tests.acceptance.test_substitute_conversions import forks_taken

RANGES = REPO_ROOT / "targets" / "ranges"


def target(module: str, function: str) -> str:
    return f"targets.ranges.{module}::{function}"


def file_of(module: str) -> str:
    return str(RANGES / f"{module}.py")


def failure_of(line: dict[str, object]) -> dict[str, object]:
    failure = line["failure"]
    assert isinstance(failure, dict), line
    return failure


def at_lines(line: dict[str, object]) -> list[tuple[object, object, object]]:
    """Each fork on a printed line, by its line, its expression and the side it took."""
    return [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(line)]


# follow-loops-and-ranges-follows-a-range-bound
def test_follows_a_range_bound() -> None:
    result = run_pyct(target("bound", "up_to"), '{"n": 2}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # each pass compares the stop with the element, a plain int, so `i == 5` records nothing;
    # the forks sit at the `for` line, at the column where the range call starts
    assert at_lines(inputs[0]) == [
        (2, [">", "n", 0], True),
        (2, [">", "n", 1], True),
        (2, [">", "n", 2], False),
    ]
    assert {fork["col"] for fork in forks_of(inputs[0])} == {13}
    five = [line for line in inputs[1:] if number(line, "n") > 5]
    assert five and covers(five[0], file_of("bound"), 4), [line["args"] for line in inputs]


# follow-loops-and-ranges-follows-a-range-from-a-start
def test_follows_a_range_from_a_start() -> None:
    result = run_pyct(target("from_a_start", "between"), '{"a": 0, "b": 2}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    once, twice = ["+", "a", 1], ["+", "a", 2]
    assert at_lines(inputs[0]) == [
        (2, [">", "b", "a"], True),
        (3, ["==", "a", 7], False),
        (2, [">", "b", once], True),
        (3, ["==", once, 7], False),
        (2, [">", "b", twice], False),
    ]
    seven = [line for line in inputs[1:] if covers(line, file_of("from_a_start"), 4)]
    assert seven, [line["args"] for line in inputs]


# follow-loops-and-ranges-follows-a-negative-step
def test_follows_a_negative_step() -> None:
    result = run_pyct(target("negative_step", "down_from"), '{"n": 2}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    back, twice = ["+", "n", -1], ["+", "n", -2]
    assert forks_taken(inputs[0]) == [
        (["<", 0, "n"], True),
        (["==", "n", 10], False),
        (["<", 0, back], True),
        (["==", back, 10], False),
        (["<", 0, twice], False),
    ]
    ten = [line for line in inputs[1:] if covers(line, file_of("negative_step"), 4)]
    assert ten, [line["args"] for line in inputs]


# follow-loops-and-ranges-follows-a-range-over-a-length
def test_follows_a_range_over_a_length() -> None:
    result = run_pyct(target("over_a_length", "find_x"), '{"s": "ab"}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    measured = ["len", "s"]
    loop = [
        (fork["expression"], fork["taken"]) for fork in forks_of(inputs[0]) if fork["line"] == 2
    ]
    assert loop == [
        ([">", measured, 0], True),
        ([">", measured, 1], True),
        ([">", measured, 2], False),
    ]
    found = [line for line in inputs[1:] if "x" in text(line, "s")]
    assert found and covers(found[0], file_of("over_a_length"), 4), [
        line["args"] for line in inputs
    ]


# follow-loops-and-ranges-follows-a-range-wherever-it-is-iterated
def test_follows_a_range_wherever_it_is_iterated() -> None:
    result = run_pyct(target("summed", "total_of"), '{"n": 2}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert at_lines(inputs[0]) == [
        (2, [">", "n", 0], True),
        (2, [">", "n", 1], True),
        (2, [">", "n", 2], False),
    ]
    big = [line for line in inputs[1:] if number(line, "n") > 5]
    assert big and covers(big[0], file_of("summed"), 4), [line["args"] for line in inputs]


# follow-loops-and-ranges-tests-membership-in-a-range-with-one-fork
def test_tests_membership_in_a_range_with_one_fork() -> None:
    result = run_pyct(target("membership", "check"), '{"port": 0, "x": 1}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert at_lines(inputs[0]) == [
        (2, ["in", "port", ["range", 1, 65536]], False),
        (4, ["in", "x", ["range", 0, 10, 2]], False),
    ]
    ports = [number(line, "port") for line in inputs[1:]]
    assert any(1 <= port <= 65535 for port in ports), ports
    evens = [number(line, "x") for line in inputs[1:] if covers(line, file_of("membership"), 5)]
    assert evens and all(x in range(0, 10, 2) for x in evens), evens


# follow-loops-and-ranges-follows-a-tracked-step
def test_follows_a_tracked_step() -> None:
    result = run_pyct(target("tracked_step", "every"), '{"k": 3}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    seed = at_lines(inputs[0])
    # the step's own forks come first, at the line of the range call, before the loop's
    assert seed[:2] == [(3, ["!=", "k", 0], True), (3, [">", "k", 0], True)]
    assert seed[2:] == [
        (3, [">", 10, "k"], True),
        (3, [">", 10, ["*", 2, "k"]], True),
        (3, [">", 10, ["*", 3, "k"]], True),
        (3, [">", 10, ["*", 4, "k"]], False),
    ]
    aim = {"file": file_of("tracked_step"), "line": 3, "col": 13, "position": 1}
    backward = [line for line in inputs[1:] if line["aim"] == aim]
    assert backward, [line["aim"] for line in inputs]
    assert number(backward[0], "k") < 0 and backward[0]["mismatch_at"] is None
    # a negative step runs no pass: the step's forks are all the line lists
    assert forks_taken(backward[0]) == [(["!=", "k", 0], True), ([">", "k", 0], False)]


# follow-loops-and-ranges-downgrades-an-untaught-range-operation
def test_downgrades_an_untaught_range_operation() -> None:
    result = run_pyct(target("untaught", "use"), '{"n": 2}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    at = "targets/ranges/untaught.py"
    assert seed["downgrades"] == [
        downgrade("__len__", 1, f"{at}:3:4"),
        downgrade("__getitem__", 1, f"{at}:4:4"),
        downgrade("__reversed__", 1, f"{at}:5:4"),
    ]
    assert at_lines(seed) == [
        (7, [">", "n", 0], True),
        (7, [">", "n", 1], True),
        (7, [">", "n", 2], False),
    ]


# follow-loops-and-ranges-leaves-an-unrewritten-range-plain
def test_leaves_an_unrewritten_range_plain() -> None:
    result = run_pyct(target("unrewritten", "plain"), '{"n": 2}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert forks_of(seed) == []
    assert seed["downgrades"] == []


# follow-loops-and-ranges-finds-the-zero-step
def test_finds_the_zero_step() -> None:
    result = run_pyct(target("zero_step", "f"), '{"k": 2}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert at_lines(inputs[0])[0] == (2, ["!=", "k", 0], True)
    zero = [line for line in inputs[1:] if number(line, "k") == 0]
    assert zero, [line["args"] for line in inputs]
    failure = failure_of(zero[0])
    assert failure["kind"] == "target_raised"
    assert str(failure["detail"]).startswith("ValueError")


# follow-loops-and-ranges-reports-a-range-of-a-string
def test_reports_a_range_of_a_string() -> None:
    result = run_pyct(target("of_a_string", "walk"), '{"s": "ab"}')

    assert result.returncode == 0, result.stderr
    failure = failure_of(first_line(result.stdout))
    assert failure["kind"] == "target_raised"
    assert str(failure["detail"]).startswith("TypeError")
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# review of follow-ranges, RNG-1: two ranges compare as Python compares them, with one fork
def test_compares_two_ranges_as_python_does() -> None:
    result = run_pyct(target("compared", "same"), '{"n": 2, "m": 2}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert at_lines(inputs[0]) == [(2, ["==", ["range", 0, "n"], ["range", 0, "m"]], True)]
    assert covers(inputs[0], file_of("compared"), 3)
    differ = [line for line in inputs[1:] if covers(line, file_of("compared"), 4)]
    assert differ, [line["args"] for line in inputs]
    assert range(number(differ[0], "n")) != range(number(differ[0], "m"))


# review of follow-ranges, RNG-2: a tracked bool searched in a range is the int it is
def test_searches_a_range_for_a_tracked_bool() -> None:
    result = run_pyct(target("bool_item", "check"), '{"x": 0}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert at_lines(inputs[0]) == [(3, ["in", [">", "x", 3], ["range", 1, 2]], False)]
    yes = [line for line in inputs[1:] if covers(line, file_of("bool_item"), 4)]
    assert yes and number(yes[0], "x") > 3, [line["args"] for line in inputs]


# review of follow-ranges, RNG-3: a tracked range is a sequence, as random.sample asks
def test_samples_a_tracked_range() -> None:
    result = run_pyct(target("sampled", "pick"), '{"n": 3}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert seed["failure"] is None, seed
