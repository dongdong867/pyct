"""Acceptance tests for the follow-values-inside-dicts-and-lists child of the
run-with-nested-arguments story.

Each test of a run spawns ``python -P -m pyct`` through the harness: a value inside an
argument is followed only if the fork it built reaches the solver and the solver's answer runs
in the seed's shape, so only a real run through the command line proves it. The test of the
accepted file reads that file.
"""

import json
import os
import re
import subprocess
import sys

import pytest

from tests.acceptance.harness import REPO_ROOT, first_line, input_lines, run_pyct
from tests.nesting import nested_text

DICT_VALUES = "targets.nested.dict_values::check"
DICT_VALUES_FILE = str(REPO_ROOT / "targets" / "nested" / "dict_values.py")
TWO_ITEMS = "targets.nested.two_items::classify"
LOOPS = "targets.nested.loops::count"
POSITIONAL_ONLY = "targets.nested.positional_only::check"
KEY_LIKE_INDEX = "targets.nested.key_like_index::compare"
KEY_LIKE_INDEX_FILE = str(REPO_ROOT / "targets" / "nested" / "key_like_index.py")
STRING_IN_LIST = "targets.nested.string_in_list::check"
OWN_ARGUMENTS = "targets.nested.own_arguments::touch"
DEEP = "targets.nested.deep::check"
RESERVED = "targets.names.solver_words::reserved"
ACCENTED = "targets.names.solver_words::accented"
# deeper than Python's default recursion limit of 1000 frames, so no step of the run may recurse
# once per level
DEPTH = 2000
ITEMS = "targets.annotations.items::echo_items"
ITEMS_AS_TEXT = "targets.annotations.items_as_text::echo_items"
KINDS = "targets.annotations.kinds::echo_kinds"
ANY_ITEMS = "targets.annotations.any_items::echo_any"
UNCHECKED = "targets.annotations.unchecked::echo_unchecked"
ACCEPTED = REPO_ROOT / "tools" / "compare_coverage" / "accepted-per-merge.jsonl"
# legacy's two fixtures of values inside a dict and a list, as the compare tool names them
LEGACY_NESTED = (
    "tests.acceptance.fixtures.structured.list_items::classify_pair",
    "tests.acceptance.fixtures.structured.nested_dict::validate_config",
)


def args_of(line: dict[str, object]) -> dict[str, object]:
    """The arguments off a printed line, narrowed so a lookup means something."""
    args = line["args"]
    assert isinstance(args, dict), line
    return args


def forks_of(line: dict[str, object]) -> list[dict[str, object]]:
    """The forks off a printed line, narrowed so a field lookup means something."""
    forks = line["forks"]
    assert isinstance(forks, list), line
    return [dict(fork) for fork in forks]


def solved(lines: list[dict[str, object]]) -> list[dict[str, object]]:
    """The lines of the inputs the solver handed back, without the seed's."""
    return [line for line in lines if line["source"] == "solver"]


def sides_of(lines: list[dict[str, object]]) -> set[tuple[str, bool]]:
    """Every fork's expression, as JSON text, with each side some line took."""
    return {
        (json.dumps(fork["expression"]), bool(fork["taken"]))
        for line in lines
        for fork in forks_of(line)
    }


def covered_of(lines: list[dict[str, object]]) -> dict[str, list[int]]:
    """Every input's covered map added up, written the way a printed line writes one."""
    union: dict[str, set[int]] = {}
    for line in lines:
        covered = line["covered"]
        assert isinstance(covered, dict), line
        for file, numbers in covered.items():
            union[str(file)] = union.get(str(file), set()) | {int(n) for n in numbers}
    return {file: sorted(numbers) for file, numbers in union.items()}


def server_of(line: dict[str, object]) -> dict[str, object]:
    """The ``server`` dict inside a line's ``config``, which must hold only that key."""
    config = args_of(line)["config"]
    assert isinstance(config, dict) and list(config) == ["server"], line
    server = config["server"]
    assert isinstance(server, dict), line
    return server


def _holds_a_server(line: dict[str, object]) -> bool:
    """Whether a line's config holds the server dict, and only that."""
    config = args_of(line)["config"]
    return isinstance(config, dict) and list(config) == ["server"]


def number(value: object) -> int:
    """A value off a line that must be a JSON integer, narrowed so a comparison means something."""
    assert isinstance(value, int) and not isinstance(value, bool), value
    return value


def items_of(line: dict[str, object]) -> list[object]:
    """A line's ``items`` list."""
    items = args_of(line)["items"]
    assert isinstance(items, list), line
    return items


# run-with-nested-arguments-flips-values-inside-a-dict
def test_flips_values_inside_a_dict() -> None:
    result = run_pyct(
        DICT_VALUES, '{"config": {"server": {"port": 100, "host": "x", "workers": 2}}}'
    )

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    # a line whose config or server the solver emptied of a key raised KeyError at its read
    servers = [server_of(line) for line in solved(lines) if _holds_a_server(line)]
    ports = [s["port"] for s in servers if "port" in s]
    assert any(isinstance(p, int) and p < 1 for p in ports), servers
    assert any(isinstance(p, int) and p > 65535 for p in ports), servers
    assert any(s.get("host") == "localhost" for s in servers), servers
    port = ["[]", ["[]", "config", "'server'"], "'port'"]
    assert ["<", port, 1] in [fork["expression"] for fork in forks_of(lines[0])]
    fork = f"fork {DICT_VALUES_FILE}:3:7  config['server']['port'] < 1  not taken"
    assert fork in result.stderr.splitlines()
    # a key no fork names keeps what the input had, and so does its value
    for server in servers:
        assert server["workers"] == 2, servers
    assert covered_of(lines) == {DICT_VALUES_FILE: list(range(2, 10))}
    # a solver line's args is a seed as it stands
    again = run_pyct(DICT_VALUES, "--args", json.dumps(args_of(solved(lines)[0])))
    assert again.returncode == 0, again.stderr


# run-with-nested-arguments-flips-two-values-inside-a-list
def test_flips_two_values_inside_a_list() -> None:
    result = run_pyct(TWO_ITEMS, '{"items": [1, 2]}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    # every item is an int, as the seed's are: the solver changes values and lengths, never kinds
    pairs = [items_of(line) for line in lines]
    assert all(type(v) is int for pair in pairs for v in pair), pairs
    answers = [items_of(line) for line in solved(lines)]
    assert any(answer and number(answer[0]) > 100 for answer in answers), answers
    pairs = [answer[:2] for answer in answers if len(answer) >= 2]
    assert any(number(second) < -50 for _, second in pairs), answers
    assert any(first == second for first, second in pairs), answers
    # two values in one argument are two unknowns, each named by its index
    last = ["==", ["[]", "items", 0], ["[]", "items", 1]]
    assert forks_of(lines[0])[-1]["expression"] == last


# run-with-nested-arguments-loops-over-a-list-and-a-dict
def test_loops_over_a_list_and_a_dict() -> None:
    # a walk over a list has no limit on its passes, so the run ends when inputs stop covering
    # new lines
    seed = '{"items": [0, 20, 5], "limits": {"a": 1, "b": 2}}'
    result = run_pyct(LOOPS, seed, "--plateau", "10")

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    # each pass of a loop records the fork on its own item, at the line that tests it, and the
    # walk over the list one fork a pass on its length (follow-lists-and-dicts-as-they-change)
    passes = [(3, [">", ["len", "items"], j]) for j in range(4)]
    items = [(4, [">", ["[]", "items", j], 10]) for j in range(3)]
    keys = [(6, [">", ["len", "limits"], j]) for j in range(3)]
    values = [(7, ["<", ["[]", "limits", "'a'"], 0]), (7, ["<", ["[]", "limits", "'b'"], 0])]
    forks = [(fork["line"], fork["expression"]) for fork in forks_of(lines[0])]
    assert [fork for fork in forks if fork[0] in (4, 7)] == items + values
    assert [fork for fork in forks if fork[0] == 3] == passes
    assert [fork for fork in forks if fork[0] == 6] == keys
    sides = sides_of(lines)
    for _, expression in items + values:
        assert {(json.dumps(expression), True), (json.dumps(expression), False)} <= sides
    # the solver may add a key to the walk over the dict, or take one away
    sizes = {len(limits) for line in lines if isinstance(limits := args_of(line)["limits"], dict)}
    assert {2, 3} <= sizes or {1, 2} <= sizes, sizes


# run-with-nested-arguments-passes-a-positional-only-parameter
@pytest.mark.parametrize("seed", ['{"value": "x"}', '{"value": "x", "strict": true}'])
def test_passes_a_positional_only_parameter(seed: str) -> None:
    result = run_pyct(POSITIONAL_ONLY, seed)

    assert result.returncode == 0, result.stderr
    matching = [
        line for line in solved(input_lines(result.stdout)) if args_of(line)["value"] == "abc"
    ]
    assert matching, result.stdout
    assert [fork["expression"] for fork in forks_of(matching[0])] == [["==", "value", "'abc'"]]


# run-with-nested-arguments-matches-legacy-on-its-nested-fixtures
def test_holds_no_accepted_difference_for_the_nested_fixtures() -> None:
    # the rows themselves are the compare tool's to check, in
    # tests/compare_coverage/acceptance/test_nested_fixtures.py; a record here would let a
    # closed gap reopen unseen
    records = [json.loads(line) for line in ACCEPTED.read_text().splitlines()[1:]]
    assert [record for record in records if record["target"] in LEGACY_NESTED] == []


# run-with-nested-arguments-quotes-a-key-that-looks-like-an-index
def test_quotes_a_key_that_looks_like_an_index() -> None:
    result = run_pyct(KEY_LIKE_INDEX, json.dumps({"d": {"0": 1, "it's": 2}}))

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    expression = [">", ["[]", "d", "'0'"], ["[]", "d", '"it\'s"']]
    # each key is looked up first, written as Python quotes it
    assert [fork["expression"] for fork in forks_of(lines[0])] == [
        ["in", "'0'", "d"],
        ["in", '"it\'s"', "d"],
        expression,
    ]
    fork = f"fork {KEY_LIKE_INDEX_FILE}:2:7  d['0'] > d[\"it's\"]  not taken"
    assert fork in result.stderr.splitlines()
    assert any(fork["taken"] for line in solved(lines) for fork in forks_of(line)), lines


# run-with-nested-arguments-indexes-a-string-inside-a-list
def test_indexes_a_string_inside_a_list() -> None:
    result = run_pyct(STRING_IN_LIST, '{"items": ["ab"]}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    seed = lines[0]
    long_enough = [">", ["len", ["[]", "items", 0]], 2]
    assert [(fork["expression"], fork["taken"]) for fork in forks_of(seed)] == [
        ([">", ["len", "items"], 0], True),
        (long_enough, False),
    ]
    failure = seed["failure"]
    assert isinstance(failure, dict) and failure["kind"] == "target_raised", seed
    assert "IndexError" in str(failure["detail"]), seed
    # the solver may also empty the list, which the index before the string's then raises on
    firsts = [str(items_of(line)[0]) for line in solved(lines) if items_of(line)]
    assert any(len(first) >= 3 for first in firsts), firsts
    assert any(len(first) >= 3 and first[2] == "x" for first in firsts), firsts


# run-with-nested-arguments-gives-each-input-its-own-arguments
@pytest.mark.parametrize("where", [(), ("--in-process",)], ids=["own-process", "in-process"])
def test_gives_each_input_its_own_arguments(where: tuple[str, ...]) -> None:
    # in pyct's own process the inputs share every other state, so the copy is what holds it
    result = run_pyct(OWN_ARGUMENTS, '{"items": [0], "config": {}}', *where)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    # the target appends None to items and writes True into config; no later input sees either
    assert [line["failure"] for line in lines] == [None] * len(lines)
    for line in lines:
        assert None not in items_of(line), line
        config = args_of(line)["config"]
        assert isinstance(config, dict) and config.get("seen") is not True, line
    # an answer may empty items, which the flip of its length check asks for
    firsts = [items_of(line)[:1] for line in solved(lines)]
    assert any(first and number(first[0]) > 5 for first in firsts), lines


# run-with-nested-arguments-leaves-other-annotations-unchecked
def test_leaves_other_annotations_unchecked() -> None:
    result = run_pyct(UNCHECKED, '{"p": ["a", "b"], "q": {"1": 2}, "r": ["x"]}')

    assert result.returncode == 0, result.stderr
    assert first_line(result.stdout)["args"] == {"p": ["a", "b"], "q": {"1": 2}, "r": ["x"]}


# run-with-nested-arguments-refuses-an-item-that-contradicts-its-annotation
@pytest.mark.parametrize("target", [ITEMS, ITEMS_AS_TEXT])
def test_refuses_an_item_that_contradicts_its_annotation(target: str) -> None:
    result = run_pyct(target, '{"xs": [1, true, "2"], "cfg": {"a": ["b", 3]}}')

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    lines = result.stderr.splitlines()
    assert 'xs[2] must be an int, got "2"' in lines
    assert "cfg['a'][1] must be a str, got 3" in lines
    # a bool is an int to Python, so the item before it passes
    assert "xs[1]" not in result.stderr


# run-with-nested-arguments-refuses-a-container-of-the-wrong-kind
def test_refuses_a_container_of_the_wrong_kind() -> None:
    result = run_pyct(KINDS, '{"items": {"a": 1}, "cfg": [1]}')

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    lines = result.stderr.splitlines()
    assert 'items must be a list, got {"a": 1}' in lines
    assert "cfg must be a dict, got [1]" in lines


# run-with-nested-arguments: a list or dict annotation checks the kind whatever its items are
def test_refuses_the_wrong_kind_under_items_it_does_not_check() -> None:
    result = run_pyct(ANY_ITEMS, '{"cfg": [1], "xs": [1, null, "a"]}')

    assert result.returncode == 2, result.stderr
    assert result.stdout == ""
    lines = result.stderr.splitlines()
    assert "cfg must be a dict, got [1]" in lines
    # an item of a union of plain types is checked against the union, null for None
    assert 'xs[2] must be an int or null, got "a"' in lines
    assert "xs[1]" not in result.stderr
    assert run_pyct(ANY_ITEMS, '{"cfg": {"k": [1]}, "xs": [1, null]}').returncode == 0


# run-with-nested-arguments: a value inside an argument, nested as deep as the seed goes
def test_follows_a_value_nested_past_the_recursion_limit() -> None:
    seed: dict[str, object] = {"a": 0}
    for _ in range(DEPTH - 1):
        seed = {"a": seed}

    # each lookup records whether its key is there, and a line whose dict the solver emptied
    # raises there and covers nothing new, so the run ends when inputs stop covering lines.
    # Each access counts a node a step, so a line prints its forks until they fill the line's
    # budget, and each later fork, `node > 5` last, as one cut part
    result = run_pyct(DEEP, json.dumps({"config": seed}), "--plateau", "1", timeout=90)

    assert result.returncode == 0, result.stderr[-2000:]
    lines = input_lines(result.stdout)
    assert lines[0]["failure"] is None and len(forks_of(lines[0])) == DEPTH + 1
    node = args_of(lines[1])["config"]
    for _ in range(DEPTH):
        assert isinstance(node, dict)
        node = node["a"]
    assert isinstance(node, int) and node > 5 and lines[1]["failure"] is None
    trace = result.stderr.split("\ncovered ")[0]
    cut = re.search(r"cut the expressions of (\d+) forks, from position (\d+) on", trace)
    assert cut is not None and int(cut[1]) + int(cut[2]) == DEPTH + 1, trace[-2000:]
    assert trace.splitlines()[-2].endswith("deep.py:5:7  ...(3 nodes)  not taken")


# a parameter named as one of the solver's own words, or past ASCII, is a leaf like any other
def test_flips_a_fork_on_a_parameter_named_as_a_solver_word() -> None:
    result = run_pyct(RESERVED, '{"div": 0}')

    assert result.returncode == 0, result.stderr
    answers = [args_of(line)["div"] for line in solved(input_lines(result.stdout))]
    assert len(answers) == 1 and isinstance(answers[0], int) and answers[0] > 3, answers


def test_flips_a_fork_on_a_parameter_named_past_ascii() -> None:
    result = run_pyct(ACCENTED, '{"café": "x"}')

    assert result.returncode == 0, result.stderr
    assert [args_of(line)["café"] for line in solved(input_lines(result.stdout))] == ["é"]


def _seed_limits_of_a_process_started_as_pyct() -> tuple[int, int]:
    """`tests.nesting.seed_limits` in a process started as the harness starts pyct's.

    Each limit follows the stack below the reader and the writer, and a test process runs
    them under more frames than pyct's own does.
    """
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    probe = [sys.executable, "-P", "-m", "tests.nesting"]
    result = subprocess.run(
        probe, cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=True
    )
    write, read = result.stdout.split()
    return int(write), int(read)


# run-with-nested-arguments: a seed nested past what a line can hold is refused before it runs
def test_refuses_a_seed_too_deep_to_write_back() -> None:
    write, read = _seed_limits_of_a_process_started_as_pyct()
    if write >= read:
        pytest.skip("this Python refuses to read a seed before it is too deep to write")

    # inside the window, so a frame or two more or less in pyct's process still lands in it
    depth = (write + read) // 2
    result = run_pyct(DEEP, '{"config": ' + nested_text(depth - 1) + "}")

    assert result.returncode == 2, result.stderr[-2000:]
    assert result.stdout == ""
    assert "too deep for pyct to write" in result.stderr
    assert "Traceback" not in result.stderr
