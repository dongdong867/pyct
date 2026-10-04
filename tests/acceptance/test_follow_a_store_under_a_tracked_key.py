"""Acceptance tests for follow-a-store-under-a-tracked-key.

A store or a removal under a key the target takes as an argument is followed: its lookup is a
fork, and every fork after it reads the dict Python holds for any answer. Each test spawns
``python -P -m pyct`` through the harness and holds each fork's stderr text, read as Python on
the line's arguments, against the side the line lists.
"""

import builtins
import copy
import importlib
import json
import re

import pytest

from tests.acceptance.harness import REPO_ROOT, input_lines, run_pyct, union_of
from tests.acceptance.test_lists import (
    args_of,
    downgrade_names,
    failure_detail,
    listed,
    solved,
)

MODULE = "targets.dicts.tracked_store"
FILE = REPO_ROOT / "targets" / "dicts" / "tracked_store.py"
UNTAUGHT = "targets.dicts.untaught::check"
# each run as the story words it: a budget of 20 s, in the default isolated mode
BUDGET = ("--budget", "20")
# the run's own budget, and the time pyct takes to start and to print past it
PATIENCE = 60
LOOKED_UP = ["in", "n", "d"]

# one fork line on stderr: its site, the condition as Python writes it, and its side
FORK = re.compile(r"fork (?P<file>\S+):(?P<line>\d+):\d+  (?P<text>.*)  (?P<side>taken|not taken)")


def line_of(function: str, text: str) -> int:
    """The line of the fixture's ``function`` that holds ``text``, counted from 1."""
    lines = FILE.read_text().splitlines()
    start = next(n for n, line in enumerate(lines) if line.startswith(f"def {function}("))
    return next(n for n, line in enumerate(lines[start:], start + 1) if text in line)


def called(line: dict[str, object], *, int_keyed: bool = False) -> dict[str, object]:
    """The line's arguments as the target receives them: a `dict[int, X]` argument's keys are
    the ints its JSON text writes."""
    args = copy.deepcopy(args_of(line))
    written = args["d"]
    if int_keyed and isinstance(written, dict):
        args["d"] = {int(key): value for key, value in written.items()}
    return args


def plain_python(function: str, args: dict[str, object]) -> object:
    """What plain Python returns for a copy of these arguments, or the error it raises."""
    target = getattr(importlib.import_module(MODULE), function)
    try:
        return target(**copy.deepcopy(args))
    except KeyError as error:
        return error


def return_line(function: str, returned: object) -> int:
    """The line of ``function``'s `return` that hands back ``returned``."""
    return line_of(function, f"return {json.dumps(returned)}")


def forks_by_input(stderr: str) -> list[tuple[dict[str, object], list[tuple[str, bool]]]]:
    """Each input's arguments off its stderr header, and each fork line after it, as the
    condition's Python text and the side it lists."""
    inputs: list[tuple[dict[str, object], list[tuple[str, bool]]]] = []
    for entry in stderr.splitlines():
        if entry.startswith(("seed {", "solver {")):
            inputs.append((json.loads(entry.split(" ", 1)[1]), []))
        elif (fork := FORK.fullmatch(entry)) is not None and fork["file"] == str(FILE):
            inputs[-1][1].append((fork["text"], fork["side"] == "taken"))
    return inputs


def check_forks_read_as_python(stderr: str, *, int_keyed: bool = False) -> None:
    """Each fork on every line, read as Python with the line's arguments, gives its side."""
    inputs = forks_by_input(stderr)
    assert any(forks for _, forks in inputs), stderr
    for args, forks in inputs:
        given = called({"args": args}, int_keyed=int_keyed)
        for text, taken in forks:
            scope = {"__builtins__": {"len": builtins.len}}
            assert eval(text, scope, dict(given)) is taken, (args, text, taken)  # noqa: S307


def covers(line: dict[str, object], number: int) -> bool:
    """Whether a line covers that line of the fixture."""
    return number in union_of([line]).get(str(FILE), [])


def check_every_line_reaches_its_aim(
    function: str, lines: list[dict[str, object]], **how: bool
) -> None:
    """Every line reaches its aim, and covers the `return` plain Python returns from, or raises
    the KeyError plain Python raises."""
    assert [line["mismatch_at"] for line in lines] == [None] * len(lines), lines
    for line in lines:
        returned = plain_python(function, called(line, **how))
        if isinstance(returned, KeyError):
            assert failure_detail(line) == f"KeyError: {returned}", line
            continue
        assert covers(line, return_line(function, returned)), (args_of(line), returned, line)


# follow-a-store-under-a-tracked-key-counts-the-stored-key
@pytest.mark.parametrize(
    ("function", "seed", "int_keyed"),
    [
        ("int_store", {"n": 0, "d": {}}, True),
        ("untyped_store", {"n": "pyct1", "d": {}}, False),
    ],
)
def test_counts_the_stored_key(function: str, seed: dict[str, object], int_keyed: bool) -> None:
    result = run_pyct(f"{MODULE}::{function}", json.dumps(seed), *BUDGET, timeout=PATIENCE)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    first = listed(lines[0])
    store, count = line_of(function, "d[n] = 5"), line_of(function, "len(d)")
    assert [fork[1] for fork in first if fork[0] == store] == [LOOKED_UP], first
    assert [fork[2] for fork in first if fork[0] == count] == [False], first
    assert downgrade_names(lines[0]) == [], lines[0]
    two = [line for line in solved(lines) if covers(line, return_line(function, "two"))]
    assert two, [args_of(line) for line in lines]
    assert all(plain_python(function, called(line, int_keyed=int_keyed)) == "two" for line in two)
    check_every_line_reaches_its_aim(function, lines, int_keyed=int_keyed)
    check_forks_read_as_python(result.stderr, int_keyed=int_keyed)


# follow-a-store-under-a-tracked-key-reads-a-plain-key-after-the-store
def test_reads_a_plain_key_after_the_store() -> None:
    result = run_pyct(f"{MODULE}::store_named", '{"n": "a", "d": {}}', *BUDGET, timeout=PATIENCE)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    covered = union_of(lines)[str(FILE)]
    assert {return_line("store_named", value) for value in (1, 2, 0)} <= set(covered), covered
    check_every_line_reaches_its_aim("store_named", lines)
    check_forks_read_as_python(result.stderr)


# follow-a-store-under-a-tracked-key-stores-through-every-store-method
@pytest.mark.parametrize(
    "function", ["defaulted_named", "updated_named", "merged_in_place_named", "merged_named"]
)
def test_stores_through_every_store_method(function: str) -> None:
    result = run_pyct(f"{MODULE}::{function}", '{"n": "a", "d": {}}', *BUDGET, timeout=PATIENCE)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    check_every_line_reaches_its_aim(function, lines)
    named = {name for line in lines for name in downgrade_names(line)}
    assert not named & {"setdefault", "update", "__ior__", "__or__"}, named


def unsat_misses(stderr: str) -> list[str]:
    """Each `missed` line on stderr whose ask cvc5 answered unsat."""
    missed = [entry for entry in stderr.splitlines() if entry.startswith("missed ")]
    return [entry for entry in missed if entry.endswith(" unsat")]


# follow-a-store-under-a-tracked-key-walks-the-stored-key, on the target
# record-a-decided-check-as-a-fact shares with it
WALKED = "tracked_store_walk"
WALKED_FILE = REPO_ROOT / "targets" / "dicts" / "decided.py"


def walked_line(text: str) -> int:
    """The line of the shared walk target that holds ``text``."""
    lines = WALKED_FILE.read_text().splitlines()
    start = next(n for n, line in enumerate(lines) if line.startswith(f"def {WALKED}("))
    return next(n for n, line in enumerate(lines[start:], start + 1) if text in line)


def test_walks_the_stored_key() -> None:
    target = f"targets.dicts.decided::{WALKED}"
    result = run_pyct(target, '{"n": "pyct1", "d": {}}', *BUDGET, timeout=PATIENCE)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    walked = getattr(importlib.import_module("targets.dicts.decided"), WALKED)
    more = [
        line
        for line in solved(lines)
        if walked_line('return "more"') in union_of([line]).get(str(WALKED_FILE), [])
    ]
    assert more, [args_of(line) for line in lines[:10]]
    assert all(walked(**copy.deepcopy(called(line))) == "more" for line in more)
    left = [(args_of(line), line["aim"], line["mismatch_at"]) for line in lines]
    assert [entry for entry in left if entry[2] is not None] == [], len(lines)
    # the flip the story found unsat with a witness: past a key the argument holds, n's own
    walk, store = walked_line("for k in d"), walked_line("d[n]")
    held = [line for line in lines if (store, LOOKED_UP, True) in listed(line)]
    assert any((walk, [">", ["len", "d"], 1], True) in listed(line) for line in held), held[:3]
    assert unsat_misses(result.stderr) == []


# a store under a tracked key between a walk and the lookups of the keys it handed out, one
# after a popitem, and a removal between them with a second walk: no answer leaves the plan
# (review of PR #131)
@pytest.mark.parametrize(
    ("function", "seed"),
    [
        ("snapshot", {"n": "a", "d": {"x1": 1, "x2": 2}}),
        ("popped_then_stored", {"n": "a", "d": {}}),
        ("rewalked", {"n": "zz", "d": {"xx": 1, "yy": 2, "zz": 3}}),
    ],
)
def test_a_store_between_a_walk_or_popitem_and_a_lookup_keeps_every_answer_on_the_plan(
    function: str, seed: dict[str, object]
) -> None:
    result = run_pyct(f"{MODULE}::{function}", json.dumps(seed), "--budget", "5")

    assert result.returncode == 0, result.stderr
    check_every_line_reaches_its_aim(function, input_lines(result.stdout))
    check_forks_read_as_python(result.stderr)


# follow-a-store-under-a-tracked-key-removes-under-a-tracked-key
@pytest.mark.parametrize("function", ["deleted", "popped", "popped_or_none"])
def test_removes_under_a_tracked_key(function: str) -> None:
    seed = '{"n": "a", "d": {"a": 1, "b": 2}}'
    result = run_pyct(f"{MODULE}::{function}", seed, *BUDGET, timeout=PATIENCE)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    removal = line_of(function, "d[n]" if function == "deleted" else "d.pop(n")
    assert (removal, LOOKED_UP, True) in listed(lines[0]), listed(lines[0])
    assert downgrade_names(lines[0]) == [], lines[0]
    covered = union_of(lines)[str(FILE)]
    assert {return_line(function, 1), return_line(function, 0)} <= set(covered), covered
    check_every_line_reaches_its_aim(function, solved(lines))
    check_forks_read_as_python(result.stderr)


# follow-a-store-under-a-tracked-key-keeps-the-other-downgrades, which replaces the expectation
# of follow-lists-and-dicts-as-they-change-downgrades-an-untaught-dict-form
def test_keeps_the_other_downgrades() -> None:
    seed = '{"config": {"a": 1}, "name": "b"}'
    untaught = run_pyct(UNTAUGHT, seed, *BUDGET, timeout=PATIENCE)
    floats = run_pyct(f"{MODULE}::float_store", '{"x": 1.5, "d": {}}', *BUDGET, timeout=PATIENCE)

    assert untaught.returncode == 0 and floats.returncode == 0, untaught.stderr + floats.stderr
    names = downgrade_names(input_lines(untaught.stdout)[0])
    assert names == ["__and__", "__contains__", "__str__"], names
    assert "__setitem__" in downgrade_names(input_lines(floats.stdout)[0])


# follow-a-store-under-a-tracked-key-raises-a-missing-key-as-python-does
@pytest.mark.parametrize("function", ["missing_deleted", "missing_popped"])
def test_raises_a_missing_key_as_python_does(function: str) -> None:
    seed = {"n": "z", "d": {"a": 1}}
    result = run_pyct(f"{MODULE}::{function}", json.dumps(seed), *BUDGET, timeout=PATIENCE)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    removal = line_of(function, "d[n]" if function == "missing_deleted" else "d.pop(n)")
    assert (removal, LOOKED_UP, False) in listed(lines[0]), listed(lines[0])
    error = plain_python(function, called(lines[0]))
    assert isinstance(error, KeyError), error
    assert failure_detail(lines[0]) == f"KeyError: {error}", lines[0]
    taken = [line for line in solved(lines) if (removal, LOOKED_UP, True) in listed(line)]
    assert taken, [args_of(line) for line in lines]
    assert any(line["mismatch_at"] is None and line["failure"] is None for line in taken), taken


# a walk hands out the key a store under a tracked key put there, one Python shares; its lookup
# leaves the tracked key free, so a later fork on it is flipped (review of PR #131, round 2)
@pytest.mark.parametrize(
    ("function", "seed", "line", "int_keyed"),
    [
        ("own_walked", {"name": "a", "config": {}}, 'return "q"', False),
        ("own_walked_int", {"n": 0, "config": {}}, 'return "seven"', True),
    ],
)
def test_a_walked_key_python_shares_leaves_its_tracked_key_free(
    function: str, seed: dict[str, object], line: str, int_keyed: bool
) -> None:
    result = run_pyct(f"{MODULE}::{function}", json.dumps(seed), "--budget", "5")

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert line_of(function, line) in union_of(lines)[str(FILE)]
    if not int_keyed:
        assert [entry["mismatch_at"] for entry in lines] == [None] * len(lines)
    # under `dict[int, X]` an answer that adds key 0 walks it ahead of n's own, so the lookup's
    # fork for it comes before the pass the answer aimed at: one answer leaves there, as
    # before this story


# a key Python shares on a dict changed under a tracked key runs as where that change is
# Python's own, as before this story: a store through a walked shared key, a walk of a copy,
# and a literal read after a walk (review of PR #131, round 3). Each covers the line it did
@pytest.mark.parametrize(
    ("function", "seed", "line", "on_plan"),
    [
        ("stored_through_walk", {"name": "a", "config": {}}, 'return "q"', True),
        ("copied_walk", {"name": "a", "config": {}}, 'return "q"', False),
        ("walked_then_read", {"n": "a", "d": {}}, "return 1", False),
    ],
)
def test_a_key_python_shares_after_a_walk_is_not_followed(
    function: str, seed: dict[str, object], line: str, on_plan: bool
) -> None:
    result = run_pyct(f"{MODULE}::{function}", json.dumps(seed), "--budget", "5")

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert line_of(function, line) in union_of(lines)[str(FILE)]
    if on_plan:
        assert [entry["mismatch_at"] for entry in lines] == [None] * len(lines)


# a copy made before the change is not the changed dict: a walk of the changed one leaves the
# copy's lookups followed, so a tracked key's lookup in it is a fork (review of PR #131, round 4)
def test_a_copy_made_before_the_change_keeps_its_tracked_lookup() -> None:
    seed = '{"n": "pyct1", "m": "zz", "d": {}}'
    result = run_pyct(f"{MODULE}::copy_looked_up", seed, "--budget", "5")

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert return_line("copy_looked_up", 1) in union_of(lines)[str(FILE)]
    assert downgrade_names(lines[0]) == [], lines[0]


# a copy changed under a tracked key after a walk of the other dict: its own change came after
# that walk, so it is followed, and every answer reaches its aim (review of PR #131, round 5)
def test_a_copy_changed_after_the_walk_stays_followed() -> None:
    seed = '{"n": "pyct1", "m": "zz", "d": {}}'
    result = run_pyct(f"{MODULE}::copy_changed_after", seed, "--budget", "5")

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert return_line("copy_changed_after", 1) in union_of(lines)[str(FILE)]
    assert [line["mismatch_at"] for line in lines] == [None] * len(lines)
    assert "__setitem__" not in downgrade_names(lines[0]), lines[0]


# Python's own `{n: 2} | d` compares n with the key n's store put in d; recorded, that compare
# pinned n to its seed's text, which the first made-up key then took, so the flip of a later
# lookup was unsat though an input takes it (review of PR #131, round 5)
def test_a_merge_compares_no_tracked_key_with_its_own_stored_key() -> None:
    seed = '{"n": "pyct1", "d": {"bc": 2}}'
    result = run_pyct(f"{MODULE}::merged_after_store", seed, "--budget", "5")

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    merge = line_of("merged_after_store", "{n: 2} | d")
    assert [fork for fork in listed(lines[0]) if fork[0] == merge] == [], listed(lines[0])
    # the flip of the seed's own `'bc' in d`, an input without "bc", is answered and reached
    flipped = next(at for at, fork in enumerate(listed(lines[0])) if fork[1] == ["in", "'bc'", "d"])
    items = line_of("merged_after_store", '("bc", 0) in d.items()')
    reached = [
        args_of(line)["d"]
        for line in solved(lines)
        if aimed_at(line) == (items, flipped) and line["mismatch_at"] is None
    ]
    assert any(isinstance(d, dict) and "bc" not in d for d in reached), len(lines)


def aimed_at(line: dict[str, object]) -> tuple[object, object] | None:
    """The line and the position of the fork a solver line aimed at, None for the seed's."""
    aim = line["aim"]
    return None if not isinstance(aim, dict) else (aim["line"], aim["position"])


# a merge with a tracked key equal to a key the argument holds: Python's own compare there is
# the target's choice, recorded, so its other side is asked (review of PR #131, round 6)
def test_a_merge_compares_a_tracked_key_with_the_argument_s_equal_key() -> None:
    result = run_pyct(f"{MODULE}::merged_held", '{"n": "b", "d": {"b": 1}}', "--budget", "5")

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert return_line("merged_held", 2) in union_of(lines)[str(FILE)]
