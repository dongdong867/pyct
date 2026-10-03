"""Acceptance tests for print-a-builtin-in-a-fork-as-python-calls-it.

Each test spawns ``python -P -m pyct`` through the harness and reads the seed's fork lines on
stderr, since the fork line is what a person reads a condition from.
"""

from tests.acceptance.harness import first_line, forks_of, run_pyct

ABOVE = "targets.ints.printed_calls::above"
CALLS = "targets.ints.printed_calls::calls"
NEGATIONS = "targets.ints.printed_calls::negations"
METHODS = "targets.strs.printed_methods::check"
IS_INTEGER = "targets.floats.is_integer::whole"


def seed_conditions(stderr: str) -> list[str]:
    """The condition on each of the seed's fork lines, in order.

    The seed's trace is the first, and it ends on its ``ended`` line. A fork line reads
    ``fork <site>  <condition>  <side>``, two spaces around the condition.
    """
    lines = stderr.splitlines()
    seed = lines[: next(i for i, line in enumerate(lines) if line.startswith("ended "))]
    # the site and the side hold no two spaces, so a condition that holds them, `'  '`, stays whole
    return [line.split("  ", 1)[1].rsplit("  ", 1)[0] for line in seed if line.startswith("fork ")]


# print-a-builtin-in-a-fork-as-python-calls-it-prints-a-builtin-as-a-call
def test_prints_a_builtin_as_a_call() -> None:
    result = run_pyct(ABOVE, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    assert seed_conditions(result.stderr) == ["abs(x) > 3"]
    # the stdout line keeps the head's name, as it did before
    assert [fork["expression"] for fork in forks_of(first_line(result.stdout))] == [
        [">", ["abs", "x"], 3]
    ]


# print-a-builtin-in-a-fork-as-python-calls-it-prints-a-method-on-its-receiver
def test_prints_a_method_on_its_receiver() -> None:
    strings = run_pyct(METHODS, '{"s": "b", "n": 0}')
    floats = run_pyct(IS_INTEGER, '{"x": 2.5}')

    assert strings.returncode == 0, strings.stderr
    assert floats.returncode == 0, floats.stderr
    assert seed_conditions(strings.stderr) == ["s.upper() == 'A'", "s.find('a') < n"]
    assert seed_conditions(floats.stderr) == ["x.is_integer()"]


# print-a-builtin-in-a-fork-as-python-calls-it-adds-no-parentheses-around-a-call
def test_adds_no_parentheses_around_a_call() -> None:
    result = run_pyct(CALLS, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    assert seed_conditions(result.stderr) == [
        "-abs(x) < -3",
        "abs(x) ** 2 > 9",
        "abs(x - 1) > 3",
        "abs(abs(x) - 5) > 1",
    ]


# print-a-builtin-in-a-fork-as-python-calls-it-prints-a-unary-operator-against-its-operand
def test_prints_a_unary_operator_against_its_operand() -> None:
    result = run_pyct(NEGATIONS, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    assert seed_conditions(result.stderr) == ["-x < 3", "-(x + 1) > 0", "--x > 1"]
