"""Acceptance tests for follow-lists-as-they-change, the lists child of
follow-lists-and-dicts-as-they-change.

Each test spawns ``python -P -m pyct`` through the harness: a list is followed only if the fork
its length or its change built reaches the solver, and the solver's answer comes back as a list
of the new length that Python runs down the side it was aimed at.
"""

import json

import pytest

from tests.acceptance.harness import (
    REPO_ROOT,
    first_line,
    forks_of,
    input_lines,
    run_pyct,
    summary_line,
    union_of,
)

LISTS = REPO_ROOT / "targets" / "lists"
EMPTIES = "targets.lists.empties::check"
EMPTIES_FILE = str(LISTS / "empties.py")
REACHES = "targets.lists.reaches_an_index::check"
LOOP = "targets.lists.loop_passes::count"
LOOP_FILE = str(LISTS / "loop_passes.py")
TRACKED_INDEX = "targets.lists.tracked_index::check"
SEARCH = "targets.lists.search_and_compare::check"
APPEND = "targets.lists.append::check"
APPEND_FILE = str(LISTS / "append.py")
CHANGES = "targets.lists.changes"
NEW_SHAPE = "targets.lists.new_shape::check"
FILLS = "targets.lists.fills"
ROWS = "targets.lists.rows::check"
THOUSANDS = "targets.lists.thousands::gather"
MILLION = "targets.lists.million"
MILLION_FILE = str(LISTS / "million.py")
LEN = "targets.lists.length::check"
LENGTH_BOUNDS = "targets.lists.length_bounds"
UNTAUGHT = "targets.lists.untaught::check"
OUTSIDE = "targets.lists.outside_change::check"
RAISES = "targets.lists.raises"

# a walk over a list has no limit on its passes (follow-loops-and-ranges), so a run over a target
# that walks one ends when inputs stop covering new lines rather than when no fork is left
UNTIL_NO_GAIN = ("--plateau", "10")

# the changes that walk the list: a search compares item after item, and a sort takes each
WALKING = ("removed", "sorted_in_place")

# a fresh copy of the argument per change, as targets/lists/changes.py writes each
CHANGED = (
    "appended",
    "extended",
    "inserted",
    "popped",
    "removed",
    "assigned",
    "deleted",
    "deleted_slice",
    "assigned_slice",
    "reversed_in_place",
    "sorted_in_place",
    "copied",
    "added",
    "added_in_place",
    "repeated",
    "repeated_in_place",
    "sliced",
)


def args_of(line: dict[str, object]) -> dict[str, object]:
    """The arguments off a printed line, narrowed so a lookup means something."""
    args = line["args"]
    assert isinstance(args, dict), line
    return args


def items_of(line: dict[str, object], name: str = "items") -> list[object]:
    """One list argument off a printed line."""
    items = args_of(line)[name]
    assert isinstance(items, list), line
    return items


def listed(line: dict[str, object]) -> list[tuple[object, object, object]]:
    """Each fork of a line as its line, its expression and the side it took."""
    return [(fork["line"], fork["expression"], fork["taken"]) for fork in forks_of(line)]


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


def downgrade_names(line: dict[str, object]) -> list[str]:
    """The names of a line's downgrades, in call order."""
    downgrades = line["downgrades"]
    assert isinstance(downgrades, list), line
    return [str(entry["name"]) for entry in downgrades]


def failure_detail(line: dict[str, object]) -> str | None:
    """What a line says the target raised, or None when it raised nothing."""
    failure = line["failure"]
    if failure is None:
        return None
    assert isinstance(failure, dict) and failure["kind"] == "target_raised", line
    return str(failure["detail"])


def fork_line(stderr: str, file: str, line: int, text: str, taken: bool) -> bool:
    """Whether stderr holds the fork line for that fork, at any column."""
    side = "taken" if taken else "not taken"
    return any(
        entry.startswith(f"fork {file}:{line}:") and entry.endswith(f"  {text}  {side}")
        for entry in stderr.splitlines()
    )


def number(value: object) -> int:
    """A value off a line that must be a JSON integer, narrowed so a comparison means something."""
    assert isinstance(value, int) and not isinstance(value, bool), value
    return value


def answered_every_fork(stdout: str) -> bool:
    """Whether the solver answered every question, sat or unsat, and never ran out of time."""
    solver = summary_line(stdout)["solver"]
    assert isinstance(solver, dict), stdout
    return (solver["unknown"], solver["timeout"]) == (0, 0)


def is_access(part: object) -> bool:
    """Whether a part is an access to a value inside an argument: a chain of `["[]", ..., key]`
    steps, each key a number or a string literal, down to a parameter's name."""
    while isinstance(part, list) and len(part) == 3 and part[0] == "[]":
        if isinstance(part[2], list):
            return False
        part = part[1]
    return isinstance(part, str) and not part.startswith(("'", '"'))


def printed_nodes(expression: object) -> int:
    """Nodes of an expression as a line prints it, counted on a stack of its own: a list and
    each leaf one node apiece, and an access one node, the name the line's args find it by."""
    nodes, stack = 0, [expression]
    while stack:
        part = stack.pop()
        nodes += 1
        if isinstance(part, list) and not is_access(part):
            stack.extend(part[1:])
    return nodes


def cut_counts(expression: object) -> list[object]:
    """The N of every cut part `["...", N]` in a printed expression, on a stack of its own."""
    counts, stack = [], [expression]
    while stack:
        part = stack.pop()
        if isinstance(part, list) and part and part[0] == "...":
            counts.append(part[1])
        elif isinstance(part, list):
            stack.extend(part[1:])
    return counts


# follow-lists-and-dicts-as-they-change-empties-a-list
def test_empties_a_list() -> None:
    result = run_pyct(EMPTIES, '{"items": [1, 2]}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert listed(lines[0]) == [
        (2, ["!=", ["len", "items"], 0], True),
        (4, [">=", ["len", "items"], 1], True),
        (4, [">", ["[]", "items", -1], 5], False),
    ]
    assert fork_line(result.stderr, EMPTIES_FILE, 2, "len(items) != 0", True)
    answers = [items_of(line) for line in solved(lines)]
    assert [] in answers, answers
    assert any(answer and number(answer[-1]) > 5 for answer in answers), answers
    assert union_of(lines) == {EMPTIES_FILE: [2, 3, 4, 5, 6]}


# follow-lists-and-dicts-as-they-change-lengthens-a-list-to-reach-an-index
def test_lengthens_a_list_to_reach_an_index() -> None:
    result = run_pyct(REACHES, '{"items": [1, 2]}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert listed(lines[0]) == [(2, [">", ["len", "items"], 3], False)]
    assert "IndexError" in str(failure_detail(lines[0]))
    answers = [items_of(line) for line in solved(lines)]
    assert any(len(answer) >= 4 and answer[:2] == [1, 2] for answer in answers), answers
    reached = [line for line in lines if len(items_of(line)) >= 4]
    assert any(number(items_of(line)[3]) > 100 for line in reached), answers
    assert [">", ["[]", "items", 3], 100] in [
        fork["expression"] for line in reached for fork in forks_of(line)
    ]


# follow-lists-and-dicts-as-they-change-adds-and-drops-loop-passes
def test_adds_and_drops_loop_passes() -> None:
    result = run_pyct(LOOP, '{"items": [0, 20]}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    passes = [(3, [">", ["len", "items"], j], j < 2) for j in range(3)]
    assert [fork for fork in listed(lines[0]) if fork[0] == 3] == passes
    for j in range(3):
        assert fork_line(result.stderr, LOOP_FILE, 3, f"len(items) > {j}", j < 2)
    lengths = [len(items_of(line)) for line in solved(lines)]
    assert 3 in lengths and any(length < 2 for length in lengths), lengths
    # one fork on each item a line has, at the line that tests it
    for line in lines:
        items = items_of(line)
        on_items = [fork[1] for fork in listed(line) if fork[0] == 4]
        assert on_items == [[">", ["[]", "items", j], 10] for j in range(len(items))], line


# follow-lists-and-dicts-as-they-change-follows-a-tracked-index
def test_follows_a_tracked_index() -> None:
    result = run_pyct(TRACKED_INDEX, '{"items": [1, 2], "i": 0}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert listed(lines[0]) == [
        (2, [">", ["len", "items"], "i"], True),
        (2, [">=", ["len", "items"], ["-", "i"]], True),
        (2, ["==", ["[]", "items", "i"], 7], False),
    ]
    answers = [args_of(line) for line in solved(lines)]
    in_range = [
        a
        for a in answers
        if -len(items_of({"args": a})) <= number(a["i"]) < len(items_of({"args": a}))
    ]
    assert any(items_of({"args": a})[number(a["i"])] == 7 for a in in_range), answers
    assert any(number(a["i"]) < 0 for a in answers), answers
    past = [line for line in solved(lines) if number(args_of(line)["i"]) >= len(items_of(line))]
    assert past and all("IndexError" in str(failure_detail(line)) for line in past), answers


# follow-lists-and-dicts-as-they-change-searches-and-compares-lists-as-python-does
def test_searches_and_compares_lists_as_python_does() -> None:
    result = run_pyct(SEARCH, '{"items": [0]}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    seed = listed(lines[0])
    assert seed[:3] == [
        (2, [">", ["len", "items"], 0], True),
        (2, ["==", ["[]", "items", 0], 7], False),
        (2, [">", ["len", "items"], 1], False),
    ]
    assert (4, ["==", ["len", "items"], 2], False) in seed
    answers = [items_of(line) for line in lines]
    assert any(7 in answer for answer in answers), answers
    assert [1, 2] in answers, answers
    # both sides of `items < [5]`, each as Python answers it for that line's items
    five: list[object] = [5]
    below = [answer < five for answer in answers if 7 not in answer and answer != [1, 2]]
    assert True in below and False in below, answers
    assert [line["mismatch_at"] for line in solved(lines)] == [None] * len(solved(lines))


# follow-lists-and-dicts-as-they-change-follows-an-append
def test_follows_an_append() -> None:
    result = run_pyct(APPEND, '{"items": [1, 2], "x": 0}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    fork = ["==", ["[]", ["+", "items", ["[,]", "x"]], 2], 42]
    assert (3, fork, False) in listed(lines[0])
    assert fork_line(result.stderr, APPEND_FILE, 3, "(items + [x])[2] == 42", False)
    hits = [args_of(line) for line in solved(lines) if (3, fork, True) in listed(line)]
    assert any(
        (a["x"] == 42 and len(items_of({"args": a})) == 2)
        or (len(items_of({"args": a})) > 2 and items_of({"args": a})[2] == 42)
        for a in hits
    ), hits


# follow-lists-and-dicts-as-they-change-follows-every-list-change
@pytest.mark.parametrize("name", CHANGED)
def test_follows_every_list_change(name: str) -> None:
    flags = UNTIL_NO_GAIN if name in WALKING else ()
    result = run_pyct(f"{CHANGES}::{name}", '{"items": [1, 2, 3, 4, 5, 6]}', *flags)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    expressions = [fork["expression"] for fork in forks_of(lines[0])]
    literal = [
        json.dumps(expression)
        for expression in expressions
        if isinstance(expression, list) and expression[0] == "==" and expression[2] == 0
    ]
    assert literal, lines[0]
    sides = sides_of(lines)
    for expression in literal:
        assert {(expression, True), (expression, False)} <= sides, (expression, sides)
    # each input the solver handed back took the side it was aimed at: Python agrees
    assert [line["mismatch_at"] for line in solved(lines)] == [None] * len(solved(lines))
    assert all(line["downgrades"] == [] for line in lines), lines
    assert answered_every_fork(result.stdout)


# follow-lists-and-dicts-as-they-change-hands-back-the-new-shape
def test_hands_back_the_new_shape() -> None:
    result = run_pyct(NEW_SHAPE, '{"items": [5]}')

    assert result.returncode == 0, result.stderr
    grown = [line for line in solved(input_lines(result.stdout)) if len(items_of(line)) == 3]
    assert grown and items_of(grown[0])[0] == 5, result.stdout
    again = run_pyct(NEW_SHAPE, "--args", json.dumps(args_of(grown[0])))
    assert again.returncode == 0, again.stderr
    assert listed(first_line(again.stdout)) == listed(grown[0])


# follow-lists-and-dicts-as-they-change-fills-an-added-item-by-kind
@pytest.mark.parametrize(
    ("function", "seed", "kind"),
    [
        ("walk", [1], int),
        ("walk_strs", [], str),
        ("walk", [], type(None)),
        ("walk_floats", [], float),
    ],
)
def test_fills_an_added_item_by_kind(function: str, seed: list[object], kind: type) -> None:
    result = run_pyct(f"{FILLS}::{function}", json.dumps({"items": seed}), *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    grown = [
        items_of(line)
        for line in solved(input_lines(result.stdout))
        if len(items_of(line)) > len(seed)
    ]
    assert grown, result.stdout
    assert all(type(item) is kind for answer in grown for item in answer[len(seed) :]), grown
    # an answer passes the seed check whenever the seed did
    answer = json.dumps({"items": grown[0]})
    again = run_pyct(f"{FILLS}::{function}", "--args", answer, *UNTIL_NO_GAIN)
    assert again.returncode == 0, again.stderr


# follow-lists-and-dicts-as-they-change-follows-lists-inside-lists
def test_follows_lists_inside_lists() -> None:
    result = run_pyct(ROWS, '{"grid": [[]]}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    grids = [items_of(line, "grid") for line in lines]
    fork = [">", ["[]", ["[]", "grid", 0], 0], 5]
    assert any(
        (3, fork, True) in listed(line) and number(items_of(line, "grid")[0][0]) > 5  # type: ignore[index]
        for line in lines
    ), grids
    assert any(len(grid) == 2 and grid[1] == [] for grid in grids), grids


# follow-lists-and-dicts-as-they-change-flips-after-thousands-of-passes
@pytest.mark.timeout(120)
def test_flips_after_thousands_of_passes() -> None:
    seed = {"data": [1] * 3000, "items": []}
    # the budget ends the run: the loop leaves thousands of forks, each open to flip
    result = run_pyct(THOUSANDS, json.dumps(seed), "--budget", "60", *UNTIL_NO_GAIN, timeout=90)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    aimed = [(line["aim"], line["mismatch_at"]) for line in solved(lines)]
    # a solver line aims at each fork after the loop, and reaches it
    for fork in (5, 7):
        assert any(aim["line"] == fork and at is None for aim, at in aimed), aimed  # type: ignore[index]
    forks = [fork for line in lines for fork in forks_of(line)]
    assert all(printed_nodes(fork["expression"]) <= 1000 for fork in forks)
    cut = [count for fork in forks for count in cut_counts(fork["expression"])]
    assert cut, "no fork after the appends was cut"


@pytest.mark.serial
@pytest.mark.timeout(270)
# follow-lists-and-dicts-as-they-change-limits-an-answer-to-a-million-items
def test_limits_an_answer_to_a_million_items() -> None:
    # the two runs take about 11 s together on an idle machine; each limit leaves a loaded one
    # room, and fails a run that hangs
    at_limit = run_pyct(f"{MILLION}::at_the_limit", '{"items": [0]}', timeout=120)
    past_limit = run_pyct(f"{MILLION}::past_the_limit", '{"items": [0]}', timeout=120)

    assert at_limit.returncode == 0, at_limit.stderr
    longest = [items_of(line) for line in solved(input_lines(at_limit.stdout))]
    assert any(len(items) == 1_000_000 and items[-1] == 1 for items in longest)
    assert past_limit.returncode == 0, past_limit.stderr
    assert f"missed {MILLION_FILE}:8:7 unsat" in past_limit.stderr.splitlines()


# follow-lists-and-dicts-as-they-change-follows-len-of-a-list: `len(items)` goes through pyct's
# own `len`, so it is the list's length term, and an item the target appended counts
def test_follows_len_of_a_list() -> None:
    result = run_pyct(LEN, '{"items": [1]}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    seed = lines[0]
    assert seed["downgrades"] == [], seed
    appended = ["+", "items", ["[,]", 0]]
    assert [(line, expression) for line, expression, _ in listed(seed)] == [
        (3, [">", ["len", appended], 3]),
        (5, ["!=", ["len", appended], 0]),
    ]
    # the flip takes the long side: three items of the argument's, and the appended one
    long = [items_of(line) for line in solved(lines) if listed(line)[0][2]]
    assert long and all(len(items) >= 3 for items in long), lines


# follow-lists-and-dicts-as-they-change-follows-len-of-a-list: a length inside an index or a
# slice bound is read as the list's length term, and its flip is one Python agrees with
@pytest.mark.parametrize(
    ("function", "line"), [("last", 2), ("all_but_last", 9), ("named_length", 16)]
)
def test_follows_a_length_inside_an_index_or_a_slice(function: str, line: int) -> None:
    result = run_pyct(f"{LENGTH_BOUNDS}::{function}", '{"items": [1, 2]}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    # the one failure is Python's own, on an input too short to read the item
    failures = {failure_detail(line_) for line_ in lines} - {None}
    assert failures <= {"IndexError: list index out of range"}, lines
    assert [line_["mismatch_at"] for line_ in solved(lines)] == [None] * len(solved(lines))
    # the item's fork took both sides, the flip an input Python ran down the other one
    sides = {taken for line_ in lines for at, _, taken in listed(line_) if at == line}
    assert sides == {True, False}, lines


# follow-lists-and-dicts-as-they-change-downgrades-an-untaught-list-form
def test_downgrades_an_untaught_list_form() -> None:
    result = run_pyct(UNTAUGHT, '{"items": [1, 2], "n": 2}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert downgrade_names(seed) == ["__getitem__", "__mul__", "index", "__str__", "append"]
    assert [fork for fork in listed(seed) if fork[0] == 7] == []


# follow-lists-and-dicts-as-they-change-notices-a-change-outside-the-methods
def test_notices_a_change_outside_the_methods() -> None:
    result = run_pyct(OUTSIDE, '{"items": [3, 9]}')

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    downgrades = seed["downgrades"]
    assert isinstance(downgrades, list), seed
    assert [(entry["name"], entry["count"]) for entry in downgrades] == [("__getitem__", 1)]
    assert [fork for fork in listed(seed) if fork[0] == 6] == []
    assert summary_line(result.stdout)["stopped"] == "no fork to flip"


# follow-lists-and-dicts-as-they-change-reports-a-pop-or-remove-that-raises
def test_reports_a_pop_or_remove_that_raises() -> None:
    popped = run_pyct(f"{RAISES}::pop_one", '{"items": []}')
    removed = run_pyct(f"{RAISES}::remove_seven", '{"items": [1]}', *UNTIL_NO_GAIN)

    assert popped.returncode == 0, popped.stderr
    pop_lines = input_lines(popped.stdout)
    assert listed(pop_lines[0]) == [(2, ["!=", ["len", "items"], 0], False)]
    assert "IndexError" in str(failure_detail(pop_lines[0]))
    assert any(failure_detail(line) is None for line in solved(pop_lines)), pop_lines
    assert removed.returncode == 0, removed.stderr
    remove_lines = input_lines(removed.stdout)
    seed = listed(remove_lines[0])
    assert (6, ["==", ["[]", "items", 0], 7], False) in seed
    assert (6, [">", ["len", "items"], 1], False) in seed
    assert "ValueError" in str(failure_detail(remove_lines[0]))
    assert any(failure_detail(line) is None for line in solved(remove_lines)), remove_lines
