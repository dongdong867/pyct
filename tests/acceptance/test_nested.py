"""Acceptance tests for the follow-values-inside-dicts-and-lists child of the
run-with-nested-arguments story.

Each test spawns ``python -P -m pyct`` through the harness: a value inside an argument is
followed only if the fork it built reaches the solver and the solver's answer runs in the
seed's shape, so only a real run through the command line proves it.
"""

import json

import pytest

from tests.acceptance.harness import REPO_ROOT, first_line, input_lines, one_line, run_pyct

DICT_VALUES = "targets.nested.dict_values::check"
DICT_VALUES_FILE = str(REPO_ROOT / "targets" / "nested" / "dict_values.py")
TWO_ITEMS = "targets.nested.two_items::classify"
LOOPS = "targets.nested.loops::count"
POSITIONAL_ONLY = "targets.nested.positional_only::check"
KEEPS_SHAPE = "targets.nested.keeps_shape::check"
KEY_LIKE_INDEX = "targets.nested.key_like_index::compare"
KEY_LIKE_INDEX_FILE = str(REPO_ROOT / "targets" / "nested" / "key_like_index.py")
STRING_IN_LIST = "targets.nested.string_in_list::check"
OWN_ARGUMENTS = "targets.nested.own_arguments::touch"
MISSING_KEY = "targets.nested.missing_key::check"
DEEP = "targets.nested.deep::check"
# deeper than Python's default recursion limit of 1000 frames, so no step of the run may recurse
# once per level
DEPTH = 2000
ITEMS = "targets.annotations.items::echo_items"
ITEMS_AS_TEXT = "targets.annotations.items_as_text::echo_items"
KINDS = "targets.annotations.kinds::echo_kinds"
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
    servers = [server_of(line) for line in solved(lines)]
    assert any(isinstance(s["port"], int) and s["port"] < 1 for s in servers), servers
    assert any(isinstance(s["port"], int) and s["port"] > 65535 for s in servers), servers
    assert any(s["host"] == "localhost" for s in servers), servers
    port = ["[]", ["[]", "config", "'server'"], "'port'"]
    assert forks_of(lines[0])[0]["expression"] == ["<", port, 1]
    fork = f"fork {DICT_VALUES_FILE}:3:7  config['server']['port'] < 1  not taken"
    assert fork in result.stderr.splitlines()
    # the solver changes values only: every line keeps the seed's keys and the value no fork read
    for line in lines:
        server = server_of(line)
        assert list(server) == ["port", "host", "workers"], line
        assert server["workers"] == 2, line
    assert covered_of(lines) == {DICT_VALUES_FILE: list(range(2, 10))}
    # a solver line's args is a seed as it stands
    again = run_pyct(DICT_VALUES, "--args", json.dumps(args_of(solved(lines)[0])))
    assert again.returncode == 0, again.stderr


# run-with-nested-arguments-flips-two-values-inside-a-list
def test_flips_two_values_inside_a_list() -> None:
    result = run_pyct(TWO_ITEMS, '{"items": [1, 2]}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    pairs = [items_of(line) for line in lines]
    # every line's items holds two ints, so the comparisons below compare numbers
    assert all(len(pair) == 2 and all(type(v) is int for v in pair) for pair in pairs), pairs
    answers = [items_of(line) for line in solved(lines)]
    assert any(int(str(first)) > 100 for first, _ in answers), answers
    assert any(int(str(second)) < -50 for _, second in answers), answers
    assert any(first == second for first, second in answers), answers
    # two values in one argument are two unknowns, each named by its index
    last = ["==", ["[]", "items", 0], ["[]", "items", 1]]
    assert forks_of(lines[0])[-1]["expression"] == last


# run-with-nested-arguments-loops-over-a-list-and-a-dict
def test_loops_over_a_list_and_a_dict() -> None:
    result = run_pyct(LOOPS, '{"items": [0, 20, 5], "limits": {"a": 1, "b": 2}}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    # each pass of a loop records the fork on its own item, at the line that tests it
    expected = [
        (4, [">", ["[]", "items", 0], 10]),
        (4, [">", ["[]", "items", 1], 10]),
        (4, [">", ["[]", "items", 2], 10]),
        (7, ["<", ["[]", "limits", "'a'"], 0]),
        (7, ["<", ["[]", "limits", "'b'"], 0]),
    ]
    assert [(fork["line"], fork["expression"]) for fork in forks_of(lines[0])] == expected
    sides = sides_of(lines)
    for _, expression in expected:
        assert {(json.dumps(expression), True), (json.dumps(expression), False)} <= sides
    for line in lines:
        assert len(items_of(line)) == 3, line
        limits = args_of(line)["limits"]
        assert isinstance(limits, dict) and list(limits) == ["a", "b"], line


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


# run-with-nested-arguments-keeps-the-shape
def test_keeps_the_shape() -> None:
    result = run_pyct(KEEPS_SHAPE, '{"items": [0], "config": {}, "note": null}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    # the length, a key test and a null are plain: the solver never changes the shape
    assert [fork["expression"] for fork in forks_of(lines[0])] == [[">", ["[]", "items", 0], 0]]
    assert lines[0]["downgrades"] == []
    for line in lines:
        args = args_of(line)
        assert len(items_of(line)) == 1, line
        assert (args["config"], args["note"]) == ({}, None), line


# run-with-nested-arguments-quotes-a-key-that-looks-like-an-index
def test_quotes_a_key_that_looks_like_an_index() -> None:
    result = run_pyct(KEY_LIKE_INDEX, json.dumps({"d": {"0": 1, "it's": 2}}))

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    expression = [">", ["[]", "d", "'0'"], ["[]", "d", '"it\'s"']]
    assert [fork["expression"] for fork in forks_of(lines[0])] == [expression]
    fork = f"fork {KEY_LIKE_INDEX_FILE}:2:7  d['0'] > d[\"it's\"]  not taken"
    assert fork in result.stderr.splitlines()
    assert any(fork["taken"] for line in solved(lines) for fork in forks_of(line)), lines


# run-with-nested-arguments-indexes-a-string-inside-a-list
@pytest.mark.xfail(
    strict=True, reason="string indexing and its long-enough fork come with follow-string-pieces"
)
def test_indexes_a_string_inside_a_list() -> None:
    result = run_pyct(STRING_IN_LIST, '{"items": ["ab"]}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    seed = lines[0]
    long_enough = [">", ["len", ["[]", "items", 0]], 2]
    assert [(fork["expression"], fork["taken"]) for fork in forks_of(seed)] == [
        (long_enough, False)
    ]
    failure = seed["failure"]
    assert isinstance(failure, dict) and failure["kind"] == "target_raised", seed
    assert "IndexError" in str(failure["detail"]), seed
    firsts = [str(items_of(line)[0]) for line in solved(lines)]
    assert any(len(first) >= 3 for first in firsts), firsts
    assert any(len(first) >= 3 and first[2] == "x" for first in firsts), firsts


# run-with-nested-arguments-gives-each-input-its-own-arguments
@pytest.mark.parametrize("where", [(), ("--in-process",)], ids=["own-process", "in-process"])
def test_gives_each_input_its_own_arguments(where: tuple[str, ...]) -> None:
    # in pyct's own process the inputs share every other state, so the copy is what holds it
    result = run_pyct(OWN_ARGUMENTS, '{"items": [0], "config": {}}', *where)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    # the target appends to items and writes a key into config; no later input sees either
    assert [line["failure"] for line in lines] == [None] * len(lines)
    for line in lines:
        assert len(items_of(line)) == 1, line
        assert args_of(line)["config"] == {}, line
    assert any(int(str(items_of(line)[0])) > 5 for line in solved(lines)), lines


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


# run-with-nested-arguments-reports-a-missing-key-as-the-target-s-raise
def test_reports_a_missing_key_as_the_targets_raise() -> None:
    result = run_pyct(MISSING_KEY, '{"config": {"server": {}}}')

    assert result.returncode == 0, result.stderr
    # one_line reads the seed's line and then the summary line, and nothing between
    seed = one_line(result.stdout)
    failure = seed["failure"]
    assert isinstance(failure, dict) and failure["kind"] == "target_raised", seed
    assert str(failure["detail"]).startswith("KeyError"), seed
    assert seed["forks"] == []


# run-with-nested-arguments: a value inside an argument, nested as deep as the seed goes
def test_follows_a_value_nested_past_the_recursion_limit() -> None:
    seed: dict[str, object] = {"a": 0}
    for _ in range(DEPTH - 1):
        seed = {"a": seed}

    result = run_pyct(DEEP, json.dumps({"config": seed}))

    assert result.returncode == 0, result.stderr[-2000:]
    lines = input_lines(result.stdout)
    assert [line["failure"] for line in lines] == [None, None]
    node = args_of(lines[1])["config"]
    for _ in range(DEPTH):
        assert isinstance(node, dict)
        node = node["a"]
    assert isinstance(node, int) and node > 5
    assert "config" + "['a']" * DEPTH + " > 5" in result.stderr
