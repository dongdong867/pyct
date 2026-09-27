"""Acceptance tests for follow-dicts-as-they-change, the dicts child of
follow-lists-and-dicts-as-they-change.

Each test spawns ``python -P -m pyct`` through the harness: a dict is followed only if the fork
its keys, its size or its change built reaches the solver, and the solver's answer comes back
as a dict with the keys it chose, which Python runs down the side it was aimed at.
"""

import json

import pytest

from tests.acceptance.harness import REPO_ROOT, input_lines, run_pyct, summary_line
from tests.acceptance.test_lists import (
    answered_every_fork,
    args_of,
    covered_of,
    downgrade_names,
    failure_detail,
    fork_line,
    forks_of,
    listed,
    number,
    sides_of,
    solved,
)

DICTS = REPO_ROOT / "targets" / "dicts"
NAMED_KEY = "targets.dicts.named_key::check"
NAMED_KEY_FILE = str(DICTS / "named_key.py")
CHANGES = "targets.dicts.changes"
MADE_UP = "targets.dicts.made_up::check"
TRACKED_KEY = "targets.dicts.tracked_key::check"
COMPARED = "targets.dicts.compared::check"
COMPARED_FILE = str(DICTS / "compared.py")
INSIDE_LISTS = "targets.dicts.inside_lists::check"
OWN_CHANGES = "targets.dicts.own_changes::check"
UNTAUGHT = "targets.dicts.untaught::check"
ALIKE = "targets.dicts.alike::check"
MISSING_KEY = "targets.dicts.missing_key::check"
MISSING_KEY_FILE = str(DICTS / "missing_key.py")
LENGTH = "targets.dicts.length::check"
INT_KEYS = "targets.dicts.int_keys"
LAST_ITEM = "targets.dicts.last_item::check"
WALKED = "targets.dicts.walked_then_asked::check"
WALKED_MODULE = "targets.dicts.walked_then_asked"
WALKED_FILE = str(DICTS / "walked_then_asked.py")
WALK_BACK = "targets.dicts.walk_back::check"
SHAPES = "targets.dicts.walk_shapes"
SHAPES_FILE = str(DICTS / "walk_shapes.py")
LENGTH_FILE = str(DICTS / "length.py")

# a walk over a dict has no limit on its passes, so a run over a target that walks one ends when
# inputs stop covering new lines rather than when no fork is left
UNTIL_NO_GAIN = ("--plateau", "10")

# a fresh copy of the argument per change, as targets/dicts/changes.py writes each
CHANGED = (
    "assigned",
    "deleted",
    "popped",
    "popped_last",
    "defaulted",
    "updated",
    "copied",
    "merged",
    "merged_in_place",
    "keys",
    "values",
    "items",
    "reversed_keys",
)

# the changes that walk the dict, whose passes have no limit
WALKING = ("values", "items", "reversed_keys")


def dict_of(line: dict[str, object], name: str) -> dict[str, object]:
    """One dict argument off a printed line."""
    value = args_of(line)[name]
    assert isinstance(value, dict), line
    return value


# follow-lists-and-dicts-as-they-change-adds-and-removes-a-named-key
def test_adds_and_removes_a_named_key() -> None:
    result = run_pyct(NAMED_KEY, '{"order": {"total": 5}}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    seed = listed(lines[0])
    assert seed[:3] == [
        (2, ["in", "'coupon'", "order"], False),
        (4, ["in", "'tip'", "order"], False),
        (6, ["in", "'total'", "order"], True),
    ]
    # each lookup records its own fork, where it runs
    presence = [fork[0] for fork in seed if fork[1] == ["in", "'total'", "order"]]
    assert presence == [6, 8], seed
    assert fork_line(result.stderr, NAMED_KEY_FILE, 2, "'coupon' in order", False)
    orders = [dict_of(line, "order") for line in solved(lines)]
    assert any(list(order) == ["total", "coupon"] for order in orders), orders
    assert any(number(order.get("tip", 0)) > 10 for order in orders), orders
    assert any("total" in order and number(order["total"]) > 100 for order in orders), orders
    assert any("total" in order and number(order["total"]) < 0 for order in orders), orders
    missing = [line for line in solved(lines) if "total" not in dict_of(line, "order")]
    assert missing and all("KeyError" in str(failure_detail(line)) for line in missing), orders


# follow-lists-and-dicts-as-they-change-follows-every-dict-change
@pytest.mark.parametrize("name", CHANGED)
def test_follows_every_dict_change(name: str) -> None:
    flags = UNTIL_NO_GAIN if name in WALKING else ()
    result = run_pyct(f"{CHANGES}::{name}", '{"config": {"a": 1, "b": 2}}', *flags)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert forks_of(lines[0]), lines[0]
    sides = sides_of(lines)
    for fork in forks_of(lines[0]):
        expression = json.dumps(fork["expression"])
        assert {(expression, True), (expression, False)} <= sides, (expression, sides)
    # each input the solver handed back took the side it was aimed at: Python agrees
    assert [line["mismatch_at"] for line in solved(lines)] == [None] * len(solved(lines))
    assert all(line["downgrades"] == [] for line in lines), lines
    assert answered_every_fork(result.stdout)


# follow-lists-and-dicts-as-they-change-makes-up-keys-to-meet-a-count
def test_makes_up_keys_to_meet_a_count() -> None:
    result = run_pyct(MADE_UP, '{"config": {}}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert listed(lines[0]) == [(2, ["!=", ["len", "config"], 0], False)]
    configs = [dict_of(line, "config") for line in solved(lines)]
    made = [config for config in configs if list(config) == ["pyct1"]]
    assert made and all(type(config["pyct1"]) is int for config in made), configs
    fork = [">", ["[]", "config", "'pyct1'"], 10]
    above = [
        line
        for line in solved(lines)
        if list(dict_of(line, "config")) == ["pyct1"]
        and number(dict_of(line, "config")["pyct1"]) > 10
    ]
    assert above, configs
    assert any((4, fork, True) in listed(line) for line in above), above


# follow-lists-and-dicts-as-they-change-follows-a-tracked-key
def test_follows_a_tracked_key() -> None:
    result = run_pyct(TRACKED_KEY, '{"name": "kiwi", "prices": {"apple": 1}}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert listed(lines[0]) == [(2, ["in", "name", "prices"], False)]
    answers = [args_of(line) for line in solved(lines)]
    held = [a for a in answers if a["name"] in dict_of({"args": a}, "prices")]
    assert held, answers
    assert any(number(dict_of({"args": a}, "prices")[str(a["name"])]) > 5 for a in held), answers


# follow-lists-and-dicts-as-they-change-compares-dicts-as-python-does
def test_compares_dicts_as_python_does() -> None:
    result = run_pyct(COMPARED, '{"config": {}}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert listed(lines[0]) == [(2, ["==", ["len", "config"], 1], False)]
    assert {"mode": "fast"} in [dict_of(line, "config") for line in lines], lines
    assert covered_of(lines) == {COMPARED_FILE: [2, 3, 4]}


# follow-lists-and-dicts-as-they-change-follows-dicts-inside-lists
def test_follows_dicts_inside_lists() -> None:
    result = run_pyct(INSIDE_LISTS, '{"orders": [{"coupon": "x"}]}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    orders = [args_of(line)["orders"] for line in lines]
    fork = ["==", ["[]", ["[]", "orders", 0], "'coupon'"], "'SAVE'"]
    saved = [line for line in lines if (3, fork, True) in listed(line)]
    assert saved, orders
    assert any(
        isinstance(order, list) and any(isinstance(o, dict) and "coupon" not in o for o in order)
        for order in orders
    ), orders
    assert any(isinstance(order, list) and len(order) == 2 and order[1] == {} for order in orders)


# follow-lists-and-dicts-as-they-change-counts-a-dict-s-own-changes
def test_counts_a_dict_s_own_changes() -> None:
    result = run_pyct(OWN_CHANGES, '{"config": {"a": 0}}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    seed = listed(lines[0])
    assert (2, ["in", "'seen'", "config"], False) in seed
    size = ["+", ["len", "config"], 1]
    assert [fork for fork in seed if fork[0] == 3] == [
        (3, [">", size, 0], True),
        (3, [">", size, 1], True),
        (3, [">", size, 2], False),
    ]
    assert (4, [">", ["[]", "config", "'a'"], 5], False) in seed
    assert [fork for fork in seed if fork[0] == 4] == [
        (4, [">", ["[]", "config", "'a'"], 5], False)
    ]
    configs = [dict_of(line, "config") for line in solved(lines)]
    assert any("seen" in config for config in configs), configs
    assert any(number(config.get("a", 0)) > 5 for config in configs), configs
    # a walk that hands out the target's own key pins the argument's keys, so no answer adds a
    # key ahead of it: each keeps the path it was asked for, or its fork is a miss
    assert [line["mismatch_at"] for line in solved(lines)] == [None] * len(solved(lines))


# follow-lists-and-dicts-as-they-change-downgrades-an-untaught-dict-form
def test_downgrades_an_untaught_dict_form() -> None:
    result = run_pyct(UNTAUGHT, '{"config": {"a": 1}, "name": "b"}')

    assert result.returncode == 0, result.stderr
    names = downgrade_names(input_lines(result.stdout)[0])
    assert names == ["__and__", "__setitem__", "__contains__", "__str__"], names


# follow-lists-and-dicts-as-they-change-runs-alike-in-and-out-of-process
def test_runs_alike_in_and_out_of_process() -> None:
    seed = '{"items": [0], "config": {"a": 0}}'
    isolated = run_pyct(ALIKE, seed)
    in_process = run_pyct(ALIKE, seed, "--in-process")

    assert isolated.returncode == 0 and in_process.returncode == 0, isolated.stderr
    kept = ("args", "forks", "source", "aim", "mismatch_at", "failure", "downgrades")
    each = [
        [{key: line[key] for key in kept} for line in input_lines(result.stdout)]
        for result in (isolated, in_process)
    ]
    assert each[0] == each[1]
    # the target appended to items and set a key of config; the line shows them as called
    assert args_of(input_lines(isolated.stdout)[0]) == {"items": [0], "config": {"a": 0}}
    assert (4, [">", ["[]", ["+", "items", ["[,]", 1]], 0], 5], False) in listed(
        input_lines(isolated.stdout)[0]
    )


# follow-lists-and-dicts-as-they-change-reports-a-missing-key
def test_reports_a_missing_key() -> None:
    result = run_pyct(MISSING_KEY, '{"config": {"server": {}}}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    missing = ["in", "'port'", ["[]", "config", "'server'"]]
    assert (2, missing, False) in listed(lines[0])
    assert "KeyError" in str(failure_detail(lines[0]))
    assert fork_line(result.stderr, MISSING_KEY_FILE, 2, "'port' in config['server']", False)
    servers = [(line, dict_of(line, "config").get("server")) for line in solved(lines)]
    held = [line for line, server in servers if isinstance(server, dict) and "port" in server]
    assert held and any(line["failure"] is None for line in held), lines


# follow-dicts-as-they-change: `len(config)` in the target's package is the dict's size term
def test_len_of_a_dict_is_its_size() -> None:
    result = run_pyct(LENGTH, '{"config": {"a": 1}}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert downgrade_names(lines[0]) == []
    assert (3, [">", ["+", ["len", "config"], 1], 2], False) in listed(lines[0])
    assert fork_line(result.stderr, LENGTH_FILE, 3, "len(config) + 1 > 2", False)
    assert any(len(dict_of(line, "config")) >= 2 for line in solved(lines)), lines


# follow-dicts-as-they-change: an int key the solver adds under a `dict[int, X]` annotation reads
# back through `--args` as the same int key, and the same path
def test_an_int_key_reads_back_as_the_same_input() -> None:
    result = run_pyct(f"{INT_KEYS}::annotated", '{"config": {}}')

    assert result.returncode == 0, result.stderr
    lines = solved(input_lines(result.stdout))
    assert any("3" in dict_of(line, "config") for line in lines), lines
    for line in lines:
        again = run_pyct(f"{INT_KEYS}::annotated", "--args", json.dumps(args_of(line)))
        assert again.returncode == 0, again.stderr
        (seeded,) = input_lines(again.stdout)[:1]
        assert args_of(seeded) == args_of(line)
        assert listed(seeded) == listed(line)


# follow-dicts-as-they-change: where no annotation says a dict's keys are ints, the solver adds
# no int key, since `--args` would read it back as a str
def test_no_int_key_is_added_where_nothing_says_the_keys_are_ints() -> None:
    result = run_pyct(f"{INT_KEYS}::unannotated", '{"config": {}}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert listed(lines[0]) == [(10, ["in", 3, "config"], False)]
    assert [dict_of(line, "config") for line in lines] == [{}]
    misses = summary_line(result.stdout)["misses"]
    assert isinstance(misses, list) and [miss["why"] for miss in misses] == ["unsat"], misses


# follow-dicts-as-they-change: `popitem` reads the dict's last key, so an answer that adds `a`
# after `b` would pop `a`. Only `{"a": 0, "b": 9}` takes line 5, and an answer lists the
# input's keys first, so no answer pyct writes takes it: the fork is an `unknown` miss, never an
# `unsat` one, and no answer leaves the plan
def test_popitem_keeps_the_key_it_read() -> None:
    result = run_pyct(LAST_ITEM, '{"config": {"b": 9}}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert [line["mismatch_at"] for line in solved(lines)] == [None] * len(solved(lines))
    misses = summary_line(result.stdout)["misses"]
    assert isinstance(misses, list)
    assert [(miss["line"], miss["why"]) for miss in misses] == [(4, "unknown")], misses


# follow-dicts-as-they-change: a walk is not a lookup, so the first lookup after it records
# whether its key is there, and the solver is asked for the other side. Nothing reads the value
# the walk read at the key's place, so another key may stand there: `{"d": {"b": 1}}` reaches
# the target. A one-character key is the very object Python gives the literal `"a"`, so pyct
# cannot tell the lookup from one of the walk's own: its flip is a named miss, never an answer
# that leaves the plan
@pytest.mark.parametrize(("name", "key", "line"), [("check_long", "alpha", 12), ("check", "a", 4)])
def test_a_lookup_after_a_walk_records_its_fork(name: str, key: str, line: int) -> None:
    result = run_pyct(f"{WALKED_MODULE}::{name}", json.dumps({"d": {key: 1}}), *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert (line, ["in", repr(key), "d"], True) in listed(lines[0])
    assert [row["mismatch_at"] for row in solved(lines)] == [None] * len(solved(lines))
    misses = summary_line(result.stdout)["misses"]
    assert isinstance(misses, list)
    reached = line + 1 in covered_of(lines)[WALKED_FILE]
    # the literal "alpha" is not the walk's own object: an answer reaches the target
    assert reached if len(key) > 1 else reached or line in {m["line"] for m in misses}, misses


# follow-dicts-as-they-change: one more pass of a walk from the end needs a key ahead of the
# input's own, which no answer writes: the fork is an `unknown` miss, never an `unsat` one
def test_a_walk_from_the_end_reports_a_pass_it_cannot_write_as_unknown() -> None:
    result = run_pyct(WALK_BACK, '{"config": {"a": 0, "b": 0}}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert [line["mismatch_at"] for line in solved(lines)] == [None] * len(solved(lines))
    misses = summary_line(result.stdout)["misses"]
    assert isinstance(misses, list)
    assert (2, "unknown") in {(miss["line"], miss["why"]) for miss in misses}, misses
    assert (2, "unsat") not in {(miss["line"], miss["why"]) for miss in misses}, misses


# follow-dicts-as-they-change: a lookup of a key a walk handed out, even after the walk ended,
# is one no input can fail: it records no fork, so no answer that flips it leaves the plan
@pytest.mark.parametrize("name", ["sorted_walk", "listed_walk"])
@pytest.mark.parametrize("key", ["alpha", "a"])
def test_a_lookup_of_a_walked_key_after_the_walk_leaves_no_plan(name: str, key: str) -> None:
    result = run_pyct(f"{SHAPES}::{name}", json.dumps({"d": {key: 1}}), *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    lookups = [f for f in listed(lines[0]) if isinstance(f[1], list) and f[1][0] == "in"]
    # a one-character key has no copy of its own: its lookup is recorded, given its place
    assert lookups == ([] if len(key) > 1 else lookups), lookups
    assert [line["mismatch_at"] for line in solved(lines)] == [None] * len(solved(lines))


# follow-dicts-as-they-change: a literal the target writes is looked up as any other, though
# Python shares its object with the walk's key: its fork is recorded, never silently skipped
def test_a_literal_python_shares_with_a_walked_key_records_its_fork() -> None:
    result = run_pyct(f"{SHAPES}::literal_in_walk", '{"d": {"a": 1}}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert (23, ["in", "'a'", "d"], True) in listed(lines[0])
    assert [line["mismatch_at"] for line in solved(lines)] == [None] * len(solved(lines))
    misses = summary_line(result.stdout)["misses"]
    assert isinstance(misses, list)
    # `{"d": {"b": 1}}` takes the other side; where no answer pyct writes is found, it is a miss
    assert 25 in covered_of(lines)[SHAPES_FILE] or 23 in {m["line"] for m in misses}, misses


# follow-dicts-as-they-change: a key nothing reads the value of may go from where a walk passed
# it, and popitem's key may be a made-up one where nothing reads what it returned
@pytest.mark.parametrize(
    ("name", "seed", "line"),
    [("listed", '{"d": {"a": 0, "c": 0, "b": 0}}', 32), ("popped", '{"d": {"a": 1}}', 40)],
)
def test_a_key_no_fork_reads_is_free_to_go(name: str, seed: str, line: int) -> None:
    result = run_pyct(f"{SHAPES}::{name}", seed, *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert line in covered_of(lines)[SHAPES_FILE], lines
    assert [row["mismatch_at"] for row in solved(lines)] == [None] * len(solved(lines))


# follow-dicts-as-they-change: a path whose walk keeps a key in place and whose float floor
# division runs past its bound is asked without both, and a model there is `unknown`, not the
# `unsat` of the program that held them
def test_a_placed_walk_beside_a_bound_is_unknown_not_unsat() -> None:
    result = run_pyct(f"{SHAPES}::bounded", '{"d": {"a": 1}, "x": 1.0}', "--budget", "20")

    assert result.returncode == 0, result.stderr
    misses = summary_line(result.stdout)["misses"]
    assert isinstance(misses, list)
    whys = {miss["why"] for miss in misses if miss["line"] == 48}
    assert whys and "unsat" not in whys, misses


SETTLED = "targets.dicts.settled"
SETTLED_FILE = str(DICTS / "settled.py")


# see-why: a lookup of a key the path already asked about records its fork again, so the
# condition that reads it names that fork and its tries, not `no fork`, which blames the program
@pytest.mark.parametrize(
    ("function", "seed", "at", "missed"),
    [("only_a", {"a": 9}, (3, 24), 4), ("int_only", {"1": 9}, (11, 15), 12)],
)
def test_names_the_fork_of_a_key_the_path_asked_about_before(
    function: str, seed: dict[str, int], at: tuple[int, int], missed: int
) -> None:
    result = run_pyct(f"{SETTLED}::{function}", json.dumps({"d": seed}), "--plateau", "5")

    assert result.returncode == 0, result.stderr
    causes = summary_line(result.stdout)["why_uncovered"]
    assert isinstance(causes, list)
    [cause] = [entry for entry in causes if missed in entry["lines"]]
    line, col = at
    assert cause["reason"] == "not taken", cause
    assert cause["condition"] == {"file": SETTLED_FILE, "line": line, "col": col, "side": False}
    assert cause["tries"]["unsat"] == 1, cause
