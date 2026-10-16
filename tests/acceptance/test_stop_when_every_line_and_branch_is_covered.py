"""Acceptance tests for part C of the match-pyct-v1-on-the-measured-functions story.

The run stops on ``every line and branch covered``, and ``--past-full-coverage`` turns that stop
off. Each test spawns ``python -P -m pyct`` through the harness and reads the input lines, the
summary line and stderr as a person or a tool reads them after a run.
"""

from tests.acceptance.harness import REPO_ROOT, input_lines, numbers_of, run_pyct, summary_line

FULL = "every line and branch covered"


def spec(module: str, function: str) -> tuple[str, str]:
    """A target under ``targets/stop``: what the command line names, and F, its file."""
    return f"targets.stop.{module}::{function}", str(
        REPO_ROOT / "targets" / "stop" / f"{module}.py"
    )


# a loop over the input's characters; line 8 `return "medium"` needs six of them counted
COUNT_Z, COUNT_Z_FILE = spec("count_z", "test")
MEDIUM = 8
# line 4 `if c == "x":` and line 6 `if n > 1:`, each of which a seed of "xx" takes one way only
COUNT_X, COUNT_X_FILE = spec("count_x", "count")
# a list comprehension over lines 2 to 6, whose filter on line 5 leads to the element on line 3
# and back to the loop on line 4
COMPREHENSION, COMPREHENSION_FILE = spec("comprehension", "pick")
# `target` forks on its own line 8, then calls `helper`, whose line 3 only "deep" runs; nothing
# calls `other`, lines 13 to 15
HELPER, HELPER_FILE = spec("helper", "target")
# line 3 and line 4 run only when the input starts with "long", and line 4 raises
RAISES_LAST, RAISES_LAST_FILE = spec("raises_last", "check")
# one fork, whose other side runs line 6, the last line
FLIP, LAST_FORK_FILE = spec("last_fork", "flip")
# one fork, whose other side runs lines 12 and 13 and never ends
STALL, _ = spec("last_fork", "stall")


def covered_by(line: dict[str, object], file: str) -> set[int]:
    """The lines one stdout line covers in ``file``."""
    return set(numbers_of(line, "covered").get(file, []))


def stopped_on(stderr: str) -> str:
    """The reason the stderr trace ends on."""
    return stderr.splitlines()[-1].removeprefix("stopped: ")


# match-pyct-v1-on-the-measured-functions-stop-when-all-covered
def test_stops_when_every_line_and_branch_is_covered() -> None:
    result = run_pyct(COUNT_Z, '{"s": ""}', "--budget", "30", timeout=60)

    assert result.returncode == 0, result.stderr
    summary = summary_line(result.stdout)
    assert summary["stopped"] == FULL
    assert stopped_on(result.stderr) == FULL
    inputs = input_lines(result.stdout)
    medium = [i for i, line in enumerate(inputs) if MEDIUM in covered_by(line, COUNT_Z_FILE)]
    assert medium[0] == len(inputs) - 1, medium
    assert numbers_of(summary, "uncovered") == {COUNT_Z_FILE: []}


# match-pyct-v1-on-the-measured-functions-stop-waits-for-each-branch
def test_waits_for_each_branch_to_go_each_way() -> None:
    result = run_pyct(COUNT_X, '{"s": "xx"}', "--budget", "30", timeout=60)

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # the seed covers every line, yet takes neither `if` the other way
    assert covered_by(inputs[0], COUNT_X_FILE) == {2, 3, 4, 5, 6, 7, 8}
    assert len(inputs) > 1
    # the last input is the first with which a count stayed at 1 or below after an `x`: then
    # line 4 has gone to line 3 and to line 5, and line 6 to line 7 and to line 8
    assert summary_line(result.stdout)["stopped"] == FULL
    both = [i for i, line in enumerate(inputs) if _both_ifs_went_both_ways(inputs[: i + 1])]
    assert both[0] == len(inputs) - 1, [line["args"] for line in inputs]


# match-pyct-v1-on-the-measured-functions-stop-waits-for-each-branch
def test_waits_for_a_comprehension_s_filter_laid_out_over_lines() -> None:
    result = run_pyct(COMPREHENSION, '{"s": "ab"}', "--budget", "30", timeout=60)

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    # the seed's filter never held, so the run goes on to an input with a `q`, and stops there
    found = [i for i, line in enumerate(inputs) if "q" in _text(line)]
    assert found[:1] == [len(inputs) - 1], [line["args"] for line in inputs]
    assert summary_line(result.stdout)["stopped"] == FULL


def _both_ifs_went_both_ways(inputs: list[dict[str, object]]) -> bool:
    """Whether these inputs, the seed's first, sent `if c == "x"` and `if n > 1` each way."""
    texts = [_text(line) for line in inputs]
    x_and_other = any("x" in s for s in texts) and any(set(s) - {"x"} for s in texts)
    counts = {s.count("x") > 1 for s in texts}
    return x_and_other and counts == {True, False}


def _text(line: dict[str, object]) -> str:
    """The `s` argument off a printed line, narrowed so a str method means something."""
    args = line["args"]
    assert isinstance(args, dict), line
    text = args["s"]
    assert isinstance(text, str), line
    return text


# match-pyct-v1-on-the-measured-functions-stop-counts-the-functions-inputs-entered
def test_counts_the_functions_the_inputs_entered() -> None:
    result = run_pyct(HELPER, '{"s": ""}', "--budget", "30", timeout=60)

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    deep = [i for i, line in enumerate(inputs) if 3 in covered_by(line, HELPER_FILE)]
    # the run went on until an input covered line 3 of `helper`, and stopped right after it,
    # with the lines of `other` still uncovered
    assert deep == [len(inputs) - 1], [line["args"] for line in inputs]
    summary = summary_line(result.stdout)
    assert summary["stopped"] == FULL
    assert numbers_of(summary, "uncovered") == {HELPER_FILE: [13, 14, 15]}


# match-pyct-v1-on-the-measured-functions-stop-order
def test_says_no_fork_to_flip_when_the_last_input_empties_the_tree() -> None:
    result = run_pyct(FLIP, '{"x": 0}')

    assert result.returncode == 0, result.stderr
    assert len(input_lines(result.stdout)) == 2
    summary = summary_line(result.stdout)
    assert numbers_of(summary, "uncovered") == {LAST_FORK_FILE: [11, 12, 13, 14]}
    assert summary["stopped"] == "no fork to flip"


# match-pyct-v1-on-the-measured-functions-stop-order
def test_says_budget_spent_when_the_budget_ends_on_the_last_input() -> None:
    result = run_pyct(STALL, '{"x": 0}', "--budget", "3")

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert len(inputs) == 2
    assert covered_by(inputs[1], LAST_FORK_FILE) >= {11, 12, 13}
    assert summary_line(result.stdout)["stopped"] == "budget spent"


# match-pyct-v1-on-the-measured-functions-stop-can-be-turned-off
def test_goes_on_past_full_coverage_with_the_flag() -> None:
    result = run_pyct(COUNT_Z, '{"s": ""}', "--budget", "5", "--past-full-coverage")

    assert result.returncode == 0, result.stderr
    assert summary_line(result.stdout)["stopped"] == "budget spent"
    inputs = input_lines(result.stdout)
    medium = [i for i, line in enumerate(inputs) if MEDIUM in covered_by(line, COUNT_Z_FILE)]
    assert medium, [line["args"] for line in inputs]
    assert medium[0] < len(inputs) - 1


# match-pyct-v1-on-the-measured-functions-stop-counts-a-raising-input
def test_counts_the_lines_of_an_input_that_raised() -> None:
    result = run_pyct(RAISES_LAST, '{"s": ""}', "--budget", "30", timeout=60)

    assert result.returncode == 0, result.stderr
    inputs = input_lines(result.stdout)
    assert len(inputs) == 2
    last = inputs[-1]
    failure = last["failure"]
    assert isinstance(failure, dict), last
    assert failure["kind"] == "target_raised"
    assert covered_by(last, RAISES_LAST_FILE) >= {3, 4}
    # the fork on `s.endswith("q")` is still open, and the run stops all the same
    summary = summary_line(result.stdout)
    assert summary["stopped"] == FULL
    assert numbers_of(summary, "uncovered") == {RAISES_LAST_FILE: []}
