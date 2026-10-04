"""Acceptance tests for the follow-loops-over-a-string child of the follow-loops-and-ranges story.

Each test spawns ``python -P -m pyct`` through the harness: a loop is followed only if its
forks reach the tree, the tree still picks the forks around the loop, and the solver's
answers run, so only a real run through the command line proves it.
"""

from tests.acceptance.harness import (
    REPO_ROOT,
    argument,
    first_line,
    forks_of,
    input_lines,
    run_pyct,
    summary_line,
    union_of,
)
from tests.acceptance.test_str_pieces import printed_nodes
from tests.acceptance.test_strs import text

COUNTDOWN = "targets.loops.countdown::count_down"
COUNTDOWN_FILE = str(REPO_ROOT / "targets" / "loops" / "countdown.py")
FIND_X = "targets.loops.find_x::find_x"
FIND_X_FILE = str(REPO_ROOT / "targets" / "loops" / "find_x.py")
WALKS = "targets.loops.walks::walk_both"
WALKS_FILE = str(REPO_ROOT / "targets" / "loops" / "walks.py")
BEFORE_A_LOOP = "targets.loops.before_a_loop::check_then_count"
BEFORE_A_LOOP_FILE = str(REPO_ROOT / "targets" / "loops" / "before_a_loop.py")
COUNT_A = "targets.loops.count_a::count_as"
COUNT_A_FILE = str(REPO_ROOT / "targets" / "loops" / "count_a.py")
RAISES_ON_COMMA = "targets.loops.raises_on_comma::no_commas"
VOWELS = "targets.loops.vowels::count_vowels"
VOWELS_FILE = str(REPO_ROOT / "targets" / "loops" / "vowels.py")


def pass_fork(position: int, name: str = "s") -> list[object]:
    """The fork a walk records for a pass: the string has a character at ``position``."""
    return [">", ["len", name], position]


def is_pass(fork: dict[str, object]) -> bool:
    """Whether a fork is a walk's pass: a compare of a string's length with a position."""
    expression = fork["expression"]
    measured = expression[1] if isinstance(expression, list) else None
    return isinstance(measured, list) and measured[0] == "len"


def covers(line: dict[str, object], file: str, number: int) -> bool:
    """Whether one input's line covers a line of a file."""
    return number in union_of([line]).get(file, [])


# follow-loops-and-ranges-follows-a-while-loop
def test_follows_a_while_loop() -> None:
    result = run_pyct(COUNTDOWN, '{"x": 2}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # the loop's test is a fork on every pass, each on the value the pass before left
    once: list[object] = ["-", "x", 1]
    assert [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(inputs[0])] == [
        (2, [">", "x", 0], True),
        (2, [">", once, 0], True),
        (2, [">", ["-", once, 1], 0], False),
    ]
    # the run does not spend its budget lengthening the loop: the seed's first fork is flipped
    never = [line for line in inputs[1:] if argument(line, "x") <= 0]
    assert never, [line["args"] for line in inputs]
    assert [(fork["expression"], fork["taken"]) for fork in forks_of(never[0])] == [
        ([">", "x", 0], False)
    ]


# follow-loops-and-ranges-walks-a-string
def test_walks_a_string() -> None:
    result = run_pyct(FIND_X, '{"s": "ab"}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    seed_forks = forks_of(inputs[0])
    assert [(fork["expression"], fork["taken"]) for fork in seed_forks] == [
        (pass_fork(0), True),
        (["==", ["[]", "s", 0], "'x'"], False),
        (pass_fork(1), True),
        (["==", ["[]", "s", 1], "'x'"], False),
        (pass_fork(2), False),
    ]
    # the loop's forks sit at the `for` line, at the column where `s` starts
    assert {(fork["line"], fork["col"]) for fork in seed_forks[::2]} == {(2, 13)}
    exit_aim = {"file": FIND_X_FILE, "line": 2, "col": 13, "position": 4}
    longer = [line for line in inputs[1:] if line["aim"] == exit_aim]
    assert longer and longer[0]["mismatch_at"] is None, [line["aim"] for line in inputs]
    assert len(text(longer[0], "s")) >= 3
    solved = [text(line, "s") for line in inputs[1:]]
    assert "" in solved
    found = [line for line in inputs[1:] if "x" in text(line, "s")]
    assert found and covers(found[0], FIND_X_FILE, 4), solved


# follow-loops-and-ranges-walks-a-string
def test_walks_a_string_of_forty_letters() -> None:
    result = run_pyct(FIND_X, '{"s": "' + "a" * 40 + '"}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # the solver answers the walk's forks inside its limit: an x at some letter, and the exit
    # flipped for a longer string, each reaching its aim
    found = [line for line in inputs[1:] if "x" in text(line, "s")]
    assert found and covers(found[0], FIND_X_FILE, 4), [line["args"] for line in inputs]
    exit_aim = {"file": FIND_X_FILE, "line": 2, "col": 13, "position": 80}
    longer = [line for line in inputs[1:] if line["aim"] == exit_aim]
    assert longer and longer[0]["mismatch_at"] is None, [line["aim"] for line in inputs]
    assert len(text(longer[0], "s")) > 40
    # every solve answers inside its limit, but the last, which the budget may cut short
    solver = summary_line(result.stdout)["solver"]
    assert isinstance(solver, dict) and solver["timeout"] <= 1, solver


# record-decided-checks-on-lists-strings-and-second-walks-walks-a-measured-string-wherever-it-is-iterated  # noqa: E501
def test_walks_a_string_wherever_it_is_iterated() -> None:
    result = run_pyct(WALKS, '{"s": "xy", "t": "xy"}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    walked = [(fork["line"], fork["expression"]) for fork in forks_of(inputs[0]) if is_pass(fork)]
    # `any` over a generator, `zip` and `enumerate` each walk at their own line, and a full
    # pass of the zip asks both strings for a character. The first walk measured s, so each
    # later pass over s is a fact, not a fork (record-decided-checks-on-lists-strings-and-
    # second-walks): only t's passes are forks at the zip
    assert walked == [
        *((2, pass_fork(k)) for k in range(3)),
        (4, pass_fork(0, "t")),
        (4, pass_fork(1, "t")),
    ]
    # each walk's body ran on an input the solver handed back: its return line is covered
    solved = inputs[1:]
    pairs = [(text(line, "s"), text(line, "t")) for line in solved]
    at = [line for line in solved if covers(line, WALKS_FILE, 3)]
    assert at and "@" in text(at[0], "s"), pairs
    differ = [line for line in solved if covers(line, WALKS_FILE, 6)]
    assert differ and text(differ[0], "s") != text(differ[0], "t"), pairs
    dash = [line for line in solved if covers(line, WALKS_FILE, 9)]
    assert dash and "-" in text(dash[0], "s"), pairs


# follow-loops-and-ranges-reaches-a-fork-before-a-loop
def test_reaches_a_fork_before_a_loop() -> None:
    result = run_pyct(BEFORE_A_LOOP, '{"x": 3, "y": 0}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    big = [line for line in input_lines(result.stdout) if argument(line, "y") > 100]
    assert big, [line["args"] for line in input_lines(result.stdout)]
    assert covers(big[0], BEFORE_A_LOOP_FILE, 3)


# follow-loops-and-ranges-flips-a-new-side-before-a-long-loop
def test_flips_a_new_side_before_a_long_loop() -> None:
    result = run_pyct(BEFORE_A_LOOP, '{"x": 200, "y": 0}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # both sides of the loop's test ran in the seed, and `y > 100` never went the other way,
    # so the second input flips it, ahead of the loop's two hundred passes
    second = inputs[1]
    assert second["aim"] == {"file": BEFORE_A_LOOP_FILE, "line": 2, "col": 7, "position": 0}
    assert argument(second, "y") > 100
    assert covers(second, BEFORE_A_LOOP_FILE, 3)


# follow-loops-and-ranges-counts-through-a-loop
def test_counts_through_a_loop_with_in_on_each_character() -> None:
    result = run_pyct(VOWELS, '{"s": "xy"}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # the walk's pass forks at the `for` line, and each character's `in` a fork of its own at
    # the `if` line, where the call-site substitution keeps its condition
    assert [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(inputs[0])] == [
        (3, pass_fork(0), True),
        (4, ["in", ["[]", "s", 0], "'aeiou'"], False),
        (3, pass_fork(1), True),
        (4, ["in", ["[]", "s", 1], "'aeiou'"], False),
        (3, pass_fork(2), False),
    ]
    many = [line for line in inputs[1:] if sum(c in "aeiou" for c in text(line, "s")) > 2]
    assert many and covers(many[0], VOWELS_FILE, 7), [line["args"] for line in inputs]


# follow-loops-and-ranges-counts-through-a-loop
def test_counts_through_a_loop() -> None:
    result = run_pyct(COUNT_A, '{"s": "ab"}', "--budget", "10")

    assert result.returncode == 0, result.stderr
    many = [line for line in input_lines(result.stdout) if text(line, "s").count("a") >= 3]
    assert many, [line["args"] for line in input_lines(result.stdout)]
    assert covers(many[0], COUNT_A_FILE, 7)


# follow-loops-and-ranges-walks-the-empty-string
def test_walks_the_empty_string() -> None:
    # the criterion names no budget, and the solver can always lengthen a walk, so the tree
    # never empties: a budget ends the run
    result = run_pyct(FIND_X, '{"s": ""}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert [(fork["expression"], fork["taken"]) for fork in forks_of(inputs[0])] == [
        (pass_fork(0), False)
    ]
    walked = [line for line in inputs[1:] if text(line, "s")]
    assert walked and covers(walked[0], FIND_X_FILE, 3), [line["args"] for line in inputs]


# follow-loops-and-ranges-follows-a-loop-of-thousands-of-passes
def test_follows_a_loop_of_thousands_of_passes() -> None:
    result = run_pyct(COUNTDOWN, '{"x": 2000}', "--budget", "20")

    # each pass nests the value one level deeper, twice past Python's recursion limit, and
    # the line, the fork line, the journal and the solver each walk it
    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    forks = forks_of(seed)
    assert len(forks) == 2001
    assert {(fork["file"], fork["line"]) for fork in forks} == {(COUNTDOWN_FILE, 2)}
    assert all(printed_nodes(fork["expression"]) <= 1000 for fork in forks)
    # input_lines holds the summary to be the last line, after every input's
    assert summary_line(result.stdout)["stopped"] == "budget spent"


# follow-loops-and-ranges-ends-a-loop-the-solver-can-always-lengthen
def test_ends_a_loop_the_solver_can_always_lengthen() -> None:
    plateau = run_pyct(COUNTDOWN, '{"x": 2}', "--plateau", "5")
    budget = run_pyct(COUNTDOWN, '{"x": 2}', "--budget", "3")

    assert plateau.returncode == 0, plateau.stderr
    assert summary_line(plateau.stdout)["stopped"] == "no gain in 5 inputs"
    assert budget.returncode == 0, budget.stderr
    assert summary_line(budget.stdout)["stopped"] == "budget spent"


# follow-loops-and-ranges-finds-the-character-that-raises
def test_finds_the_character_that_raises() -> None:
    result = run_pyct(RAISES_ON_COMMA, '{"s": "ab"}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    raised = [line for line in input_lines(result.stdout)[1:] if "," in text(line, "s")]
    assert raised, [line["args"] for line in input_lines(result.stdout)]
    failure = raised[0]["failure"]
    assert isinstance(failure, dict), raised[0]
    assert failure["kind"] == "target_raised"
    assert str(failure["detail"]).startswith("ValueError")
