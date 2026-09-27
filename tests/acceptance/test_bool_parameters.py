"""Acceptance tests for follow-bool-parameters-and-membership, a child of
follow-booleans-and-chained-compares.

A bool parameter is a leaf the solver flips, identity is answered from the value, membership in
a set or a dict is followed element by element, and `in` and `is` are followed inside a chained
compare. Each test runs pyct through the command line, as the rest of the story's tests do.
"""

from tests.acceptance.harness import REPO_ROOT, first_line, input_lines, run_pyct
from tests.acceptance.test_bools import at, expressions, failure_of, sides
from tests.acceptance.test_ints import argument, forks_of

FLAG_PARAMETER = "targets.bools.flag_parameter::flip"
FLAG_PARAMETER_FILE = str(REPO_ROOT / "targets" / "bools" / "flag_parameter.py")
IDENTITY = "targets.bools.identity::check"
IDENTITY_FILE = str(REPO_ROOT / "targets" / "bools" / "identity.py")
HASHED_MEMBERSHIP = "targets.bools.hashed_membership::pick"
CHAIN_LINKS = "targets.bools.chain_links::band"
CHAIN_LINKS_FILE = str(REPO_ROOT / "targets" / "bools" / "chain_links.py")
BOOLS_AND_FLOATS = "targets.bools.bools_and_floats::mix"
HUNDRED = "targets.bools.hundred::within"
HUNDRED_FILE = str(REPO_ROOT / "targets" / "bools" / "hundred.py")
BOOL_SEED = "targets.bools.bool_seed::truth"
FALSE_BOOL_DIVISOR = "targets.bools.false_bool_divisor::share"
BEFORE_NONE = "targets.bools.before_none::check"
BEFORE_NONE_FILE = str(REPO_ROOT / "targets" / "bools" / "before_none.py")
TWO_FLAGS = "targets.bools.two_flags::same"
TWO_FLAGS_FILE = str(REPO_ROOT / "targets" / "bools" / "two_flags.py")


def flag_of(line: dict[str, object], name: str = "flag") -> bool:
    """One bool argument off a printed line: a JSON bool, never the int 1 or 0."""
    args = line["args"]
    assert isinstance(args, dict), line
    value = args[name]
    assert type(value) is bool, line
    return value


def placed(line: dict[str, object], number: int) -> list[tuple[object, object, object]]:
    """The column, expression and side of each fork a printed line lists at one line."""
    return [
        (fork["col"], fork["expression"], fork["taken"])
        for fork in forks_of(line)
        if fork["line"] == number
    ]


def covered(line: dict[str, object], file: str) -> list[int]:
    """The lines of one file a printed line covered."""
    lines = line["covered"]
    assert isinstance(lines, dict), line
    return lines.get(file, [])


# follow-booleans-and-chained-compares-flips-a-bool-parameter
def test_flips_a_bool_parameter() -> None:
    result = run_pyct(FLAG_PARAMETER, '{"flag": false, "x": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # the parameter tested alone is its own name, as a compare is the compare itself
    assert [(fork["expression"], fork["taken"]) for fork in forks_of(inputs[0])] == [
        ("flag", False),
        ([">", ["+", "flag", "x"], 5], False),
    ]
    fork_lines = [line for line in result.stderr.splitlines() if line.startswith("fork ")]
    assert fork_lines[0] == f"fork {FLAG_PARAMETER_FILE}:2:7  flag  not taken"
    flipped = [line for line in inputs[1:] if flag_of(line) is True]
    assert flipped, inputs
    assert any(3 in covered(line, FLAG_PARAMETER_FILE) for line in flipped)
    assert all(type(flag_of(line)) is bool for line in inputs)
    # the sum reads the bool as the int 1 or 0, so some input takes its true side too
    assert sides(inputs, [">", ["+", "flag", "x"], 5]) == {True, False}


# follow-booleans-and-chained-compares-answers-identity-from-the-value
def test_answers_identity_from_the_value() -> None:
    result = run_pyct(IDENTITY, '{"flag": false, "x": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    seed = inputs[0]
    # `is True` and `is not False` test the bool as `if flag:` does; `is None` is plainly false
    assert [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(seed)] == [
        (2, "flag", False),
        (4, "flag", False),
    ]
    assert at(seed, 6) == []
    flipped = [line for line in inputs[1:] if flag_of(line) is True]
    assert any(3 in covered(line, IDENTITY_FILE) for line in flipped), inputs


# follow-booleans-and-chained-compares-follows-membership-in-a-set-or-dict
def test_follows_membership_in_a_set_or_dict() -> None:
    result = run_pyct(HASHED_MEMBERSHIP, '{"s": "none", "n": 0}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    seed = inputs[0]
    # a literal set is searched in the order written, a module's dict in its own order
    assert at(seed, 5) == [["==", "s", "'red'"], ["==", "s", "'green'"], ["==", "s", "'blue'"]]
    assert at(seed, 7) == [["==", "n", 1], ["==", "n", 2]]
    assert all(fork["taken"] is False for fork in forks_of(seed))
    # an empty set compares with nothing
    assert at(seed, 9) == []
    texts = {str(line["args"]["s"]) for line in inputs if isinstance(line["args"], dict)}
    assert {"red", "green", "blue"} <= texts
    assert {1, 2} <= {argument(line, "n") for line in inputs}


# follow-booleans-and-chained-compares-follows-in-and-is-inside-a-chain
def test_follows_in_and_is_inside_a_chain() -> None:
    result = run_pyct(CHAIN_LINKS, '{"x": 0, "flag": false}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert placed(inputs[0], 2) == [(7, [">", "x", 0], False)]
    # the set's forks follow the link before them, at the column where the chain starts
    heads = [[(col, expression) for col, expression, _ in placed(line, 2)[:2]] for line in inputs]
    assert [(7, [">", "x", 0]), (7, ["==", "x", 1])] in heads
    assert {1, 5, 9} <= {argument(line, "x") for line in inputs}
    # `is True` at the chain's end tests the bool as `if flag:` does
    flagged = [line for line in inputs if (7, "flag", True) in placed(line, 4)]
    assert all(flag_of(line) is True for line in flagged)
    assert any(5 in covered(line, CHAIN_LINKS_FILE) for line in flagged), inputs


# follow-booleans-and-chained-compares-mixes-bools-and-floats
def test_mixes_bools_and_floats() -> None:
    result = run_pyct(BOOLS_AND_FLOATS, '{"f": 0.0, "flag": false}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # the bool is 1.0 or 0.0 beside a float, a literal or the parameter itself
    first, second = [">", ["+", "f", True], 2.5], [">", ["*", "flag", 2.5], "f"]
    assert expressions(inputs[0]) == [first, second]
    assert sides(inputs, first) == {True, False}
    assert sides(inputs, second) == {True, False}
    assert all(line["downgrades"] == [] for line in inputs)


# follow-booleans-and-chained-compares-follows-membership-up-to-a-hundred-items
def test_follows_membership_up_to_a_hundred_items() -> None:
    result = run_pyct(HUNDRED, '{"n": -1}', "--plateau", "3")

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    seed = inputs[0]
    # one `==` per element up to 100; past that Python answers, and the line names the loss
    assert at(seed, 6) == [["==", "n", k] for k in range(100)]
    assert all(fork["taken"] is False for fork in forks_of(seed))
    assert at(seed, 8) == []
    downgrades = seed["downgrades"]
    assert isinstance(downgrades, list), seed
    assert [(item["name"], item["count"]) for item in downgrades] == [("__contains__", 1)]
    found = [line for line in inputs[1:] if 0 <= argument(line, "n") <= 99]
    assert any(7 in covered(line, HUNDRED_FILE) for line in found), inputs


# follow-booleans-and-chained-compares-reads-a-bool-from-the-seed
def test_reads_a_bool_from_the_seed() -> None:
    as_bool = run_pyct(BOOL_SEED, '{"n": true}')
    as_int = run_pyct(BOOL_SEED, '{"n": 1}')

    assert as_bool.returncode == 0, as_bool.stderr
    assert as_int.returncode == 0, as_int.stderr
    # the seed decides the type, whatever the annotation says
    bool_seed, bool_solved = input_lines(as_bool.stdout)[:2]
    assert expressions(bool_seed) == ["n"]
    assert bool_solved["args"] == {"n": False}
    assert '"n": false' in as_bool.stdout.splitlines()[1]
    int_seed, int_solved = input_lines(as_int.stdout)[:2]
    assert expressions(int_seed) == [["!=", "n", 0]]
    assert int_solved["args"] == {"n": 0}
    assert type(argument(int_solved, "n")) is int


# follow-booleans-and-chained-compares-finds-the-false-bool-divisor
def test_finds_the_false_bool_divisor() -> None:
    result = run_pyct(FALSE_BOOL_DIVISOR, '{"flag": true}')

    assert result.returncode == 0, result.stderr
    seed, solved = input_lines(result.stdout)[:2]
    # the zero fork of a bool divisor is the bool itself, as `if flag:` would test it
    assert [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(seed)] == [
        (2, "flag", True)
    ]
    assert flag_of(solved) is False
    failure = failure_of(solved)
    assert failure["kind"] == "target_raised"
    assert "ZeroDivisionError" in str(failure["detail"])
    assert first_line(result.stdout)["failure"] is None


# follow-booleans-and-chained-compares-answers-identity-from-the-value
def test_two_bools_are_identical_when_they_are_equal() -> None:
    result = run_pyct(TWO_FLAGS, '{"flag": true, "other": true}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # plain Python answers `True is True`, so the seed takes the first branch
    assert placed(inputs[0], 2) == [(7, ["==", "flag", "other"], True)]
    assert 3 in covered(inputs[0], TWO_FLAGS_FILE)
    # an input that makes them differ reaches the chain, which reads them the same way, so the
    # line under it runs for no input, as in plain Python
    differ = [line for line in inputs if flag_of(line) != flag_of(line, "other")]
    assert any(6 in covered(line, TWO_FLAGS_FILE) for line in differ), inputs
    assert not any(5 in covered(line, TWO_FLAGS_FILE) for line in inputs)


# follow-booleans-and-chained-compares-follows-in-and-is-inside-a-chain
def test_a_bool_link_before_is_not_none_answers_as_plain_python() -> None:
    result = run_pyct(BEFORE_NONE, '{"flag": true, "other": false}')

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # plain Python answers `True is True is not None`, so the seed takes the first branch
    assert placed(inputs[0], 2) == [(7, "flag", True)]
    assert 3 in covered(inputs[0], BEFORE_NONE_FILE)
    assert any(5 in covered(line, BEFORE_NONE_FILE) for line in inputs)
