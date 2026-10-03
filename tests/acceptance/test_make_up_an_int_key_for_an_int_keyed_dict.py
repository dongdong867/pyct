"""Acceptance tests for make-up-an-int-key-for-an-int-keyed-dict.

A dict annotated ``dict[int, X]`` whose keys are all ints, an empty one included, meets a count
with made-up int keys: the smallest non-negative ints it does not hold and no fork names. A
line writes each as JSON text, and ``--args`` reads it back as the int.
"""

import json
import re

import pytest

from tests.acceptance.harness import REPO_ROOT, input_lines, run_pyct, summary_line, union_of
from tests.acceptance.test_dicts import UNTIL_NO_GAIN, dict_of
from tests.acceptance.test_lists import args_of, downgrade_names, listed, number, solved

DICTS = REPO_ROOT / "targets" / "dicts"
MADE_UP_INTS = "targets.dicts.made_up_ints"
MADE_UP_INTS_FILE = str(DICTS / "made_up_ints.py")
INT_ONLY = "targets.dicts.settled::int_only"
SETTLED_FILE = str(DICTS / "settled.py")

# the text JSON writes for an int, which `--args` reads back as the int under `dict[int, X]`
INT_TEXT = re.compile(r"0|-?[1-9][0-9]*")


def int_keyed(line: dict[str, object], name: str = "d") -> dict[int, object]:
    """A `dict[int, X]` argument off a printed line, as the target received it: each key an
    int's JSON text, read back as the int."""
    written = dict_of(line, name)
    assert all(INT_TEXT.fullmatch(key) for key in written), written
    return {int(key): value for key, value in written.items()}


# make-up-an-int-key-for-an-int-keyed-dict-makes-up-a-key-to-meet-a-count
def test_makes_up_a_key_to_meet_a_count() -> None:
    result = run_pyct(f"{MADE_UP_INTS}::counted", '{"d": {}}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert listed(lines[0]) == [(2, ["!=", ["len", "d"], 0], False)]
    ds = [int_keyed(line) for line in lines]
    one = [d for d in ds[1:] if list(d) == [0]]
    assert one and all(type(d[0]) is int for d in one), ds
    fork = [">", ["[]", "d", 0], 10]
    above = [line for line in solved(lines) if list(int_keyed(line)) == [0]]
    above = [line for line in above if number(int_keyed(line)[0]) > 10]
    assert above and any((4, fork, True) in listed(line) for line in above), ds


# make-up-an-int-key-for-an-int-keyed-dict: `int_only` stays behind legacy at line 12, and the
# cause is the walk's place, not a missing int key. Every path from `{"1": 9}` walks key 1 first,
# and the only flip that drops it is the line-10 lookup Python shares with the walk's key 1,
# recorded given its place. With the place it is unsat, and the answer found without it is an
# `unknown` miss, never an answer that leaves the plan; try-an-answer-found-without-a-walk-s-
# places tracks the gap
def test_int_only_misses_line_12_through_the_walk_s_place() -> None:
    result = run_pyct(INT_ONLY, '{"d": {"1": 9}}', "--plateau", "5")

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert 12 not in union_of(lines)[SETTLED_FILE], union_of(lines)
    for line in lines:
        # asserts that each key an answer holds, a made-up one included, is an int's JSON text
        int_keyed(line)
    assert [line["mismatch_at"] for line in solved(lines)] == [None] * len(solved(lines))
    misses = summary_line(result.stdout)["misses"]
    assert isinstance(misses, list)
    assert (10, 11, "unknown") in {(m["line"], m["col"], m["why"]) for m in misses}, misses


# make-up-an-int-key-for-an-int-keyed-dict-hands-the-keys-back-through-args
def test_hands_the_keys_back_through_args() -> None:
    target = f"{MADE_UP_INTS}::counted"
    result = run_pyct(target, '{"d": {}}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    made = [line for line in solved(input_lines(result.stdout)) if int_keyed(line)]
    assert made, result.stdout
    for line in made:
        again = run_pyct(target, "--args", json.dumps(args_of(line)), *UNTIL_NO_GAIN)
        # a seed the check refused would exit nonzero before its line
        assert again.returncode == 0, again.stderr
        seeded = input_lines(again.stdout)[0]
        assert args_of(seeded) == args_of(line)
        assert listed(seeded) == listed(line)


# make-up-an-int-key-for-an-int-keyed-dict-skips-held-and-named-keys
def test_skips_held_and_named_keys() -> None:
    result = run_pyct(f"{MADE_UP_INTS}::skips", '{"d": {"0": 5}}')

    assert result.returncode == 0, result.stderr
    lines = solved(input_lines(result.stdout))
    covering = [line for line in lines if 23 in union_of([line]).get(MADE_UP_INTS_FILE, [])]
    ds = [dict_of(line, "d") for line in covering]
    assert any(list(d) == ["0", "2"] and d["0"] == 5 for d in ds), lines


# make-up-an-int-key-for-an-int-keyed-dict-follows-a-tracked-int-key
def test_follows_a_tracked_int_key() -> None:
    result = run_pyct(f"{MADE_UP_INTS}::tracked", '{"n": 5, "d": {}}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert listed(lines[0]) == [(28, ["in", "n", "d"], False)]
    ds = [int_keyed(line) for line in lines]
    taken = [line for line in solved(lines) if (28, ["in", "n", "d"], True) in listed(line)]
    # Python agrees: the answer's `n` is a key its `d` holds
    assert taken and all(args_of(line)["n"] in int_keyed(line) for line in taken), ds


# make-up-an-int-key-for-an-int-keyed-dict-keeps-str-keys-elsewhere
def test_keeps_str_keys_elsewhere() -> None:
    plain = run_pyct(f"{MADE_UP_INTS}::counted_unannotated", '{"d": {}}', *UNTIL_NO_GAIN)
    str_keyed = run_pyct(f"{MADE_UP_INTS}::counted", '{"d": {"a": 1}}', *UNTIL_NO_GAIN)

    assert plain.returncode == 0 and str_keyed.returncode == 0, plain.stderr + str_keyed.stderr
    ds = [dict_of(line, "d") for line in solved(input_lines(plain.stdout))]
    assert any("pyct1" in d for d in ds), ds
    lines = input_lines(str_keyed.stdout)
    assert (3, [">", ["len", "d"], 1], False) in listed(lines[0]), listed(lines[0])
    # no key is made up: no answer holds a key besides "a", and no line takes the count past 1
    assert all(set(dict_of(line, "d")) <= {"a"} for line in lines), lines
    assert all((3, [">", ["len", "d"], 1], True) not in listed(line) for line in lines), lines
    misses = summary_line(str_keyed.stdout)["misses"]
    assert isinstance(misses, list)
    # the flips of `len(d) > 0` on the empty answer's path and of `len(d) > 1` on the seed's
    assert [(m["line"], m["why"]) for m in misses if m["line"] == 3] == [(3, "unsat")] * 2, misses
    missed = [
        e for e in str_keyed.stderr.splitlines() if e.startswith(f"missed {MADE_UP_INTS_FILE}:3:")
    ]
    assert len(missed) == 2 and all(entry.endswith(" unsat") for entry in missed), missed


INT_EQUAL = "targets.dicts.int_equal_keys"
INT_EQUAL_FILE = str(DICTS / "int_equal_keys.py")


def _own_lines(lines: list[dict[str, object]]) -> list[int]:
    return union_of(lines).get(INT_EQUAL_FILE, [])


# make-up-an-int-key-for-an-int-keyed-dict: a plain key Python's lookup makes the same as an int,
# an IntEnum member, a bool or an integral float, is looked up as that int, so its fork names the
# int and a made-up key skips it; every answer takes the side it was aimed at
@pytest.mark.parametrize(
    ("function", "forks", "lines"),
    [
        ("enum_key", [(14, ["in", 0, "d"], False)], [14, 15, 16, 17, 18]),
        (
            "bool_keys",
            [(22, ["in", 1, "d"], False), (24, ["in", 0, "d"], False)],
            [22, 23, 24, 26, 27, 28],
        ),
        ("float_key", [(32, ["in", 1, "d"], False)], [32, 33, 34, 35, 36]),
    ],
)
def test_a_key_equal_to_an_int_is_looked_up_as_the_int(
    function: str, forks: list[tuple[object, object, object]], lines: list[int]
) -> None:
    result = run_pyct(f"{INT_EQUAL}::{function}", '{"d": {}}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    printed = input_lines(result.stdout)
    assert listed(printed[0])[: len(forks)] == forks, listed(printed[0])
    assert all(line["downgrades"] == [] for line in printed), printed
    assert [line["mismatch_at"] for line in solved(printed)] == [None] * len(solved(printed))
    assert set(lines) <= set(_own_lines(printed)), _own_lines(printed)


# make-up-an-int-key-for-an-int-keyed-dict: a store or a removal under such a key looks it up as
# the int too, so a made-up key skips it and no answer leaves the plan
@pytest.mark.parametrize(
    ("function", "fork", "line"),
    [
        ("stored_float", (56, ["in", 1, "d"], False), 58),
        ("popped_bool", (63, ["in", 1, "d"], False), 65),
    ],
)
def test_a_change_under_a_key_equal_to_an_int_names_the_int(
    function: str, fork: tuple[object, object, object], line: int
) -> None:
    result = run_pyct(f"{INT_EQUAL}::{function}", '{"d": {}}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    printed = input_lines(result.stdout)
    assert listed(printed[0])[0] == fork, listed(printed[0])
    assert all(line["downgrades"] == [] for line in printed), printed
    assert [line["mismatch_at"] for line in solved(printed)] == [None] * len(solved(printed))
    assert line in _own_lines(printed), _own_lines(printed)


# make-up-an-int-key-for-an-int-keyed-dict: a key with its own `__hash__`, and a tracked bool key,
# stay downgrades; either may equal a made-up int, so the dict turns plain there, and no answer
# leaves the plan through a made-up key
@pytest.mark.parametrize(
    ("function", "seed", "downgrade"),
    [
        ("own_hash_key", {"d": {}}, "__contains__"),
        ("tracked_bool", {"b": False, "d": {}}, "__contains__"),
        ("own_hash_stored", {"d": {}}, "__setitem__"),
    ],
)
def test_a_key_pyct_does_not_follow_stays_a_downgrade(
    function: str, seed: dict[str, object], downgrade: str
) -> None:
    result = run_pyct(f"{INT_EQUAL}::{function}", json.dumps(seed), *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    printed = input_lines(result.stdout)
    assert downgrade_names(printed[0])[:1] == [downgrade], printed[0]
    assert [line["mismatch_at"] for line in solved(printed)] == [None] * len(solved(printed))


INT_EQUAL_NUMBERS = "targets.dicts.int_equal_numbers"
INT_EQUAL_NUMBERS_FILE = str(DICTS / "int_equal_numbers.py")


# make-up-an-int-key-for-an-int-keyed-dict: any other number, a Fraction, a Decimal or a float
# subclass, may equal an int, so looking it up turns a `dict[int, X]` plain
@pytest.mark.parametrize("function", ["fraction_key", "decimal_key", "float_subclass_key"])
def test_a_number_pyct_does_not_follow_turns_the_dict_plain(function: str) -> None:
    result = run_pyct(f"{INT_EQUAL_NUMBERS}::{function}", '{"d": {}}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    printed = input_lines(result.stdout)
    assert downgrade_names(printed[0])[:1] == ["__contains__"], printed[0]
    assert [line["mismatch_at"] for line in solved(printed)] == [None] * len(solved(printed))


# make-up-an-int-key-for-an-int-keyed-dict: `setdefault` and a merge with the dict on the right
# look a key equal to an int up as that int, as a store does
@pytest.mark.parametrize(
    ("function", "fork", "line"),
    [
        ("defaulted_bool", (39, ["in", 0, "d"], False), 41),
        ("defaulted_enum", (46, ["in", 0, "d"], False), 48),
        ("merged_after", (53, ["in", 1, "d"], False), 55),
    ],
)
def test_setdefault_and_a_merge_name_the_int(
    function: str, fork: tuple[object, object, object], line: int
) -> None:
    result = run_pyct(f"{INT_EQUAL_NUMBERS}::{function}", '{"d": {}}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    printed = input_lines(result.stdout)
    assert listed(printed[0])[0] == fork, listed(printed[0])
    assert all(entry["downgrades"] == [] for entry in printed), printed
    assert [entry["mismatch_at"] for entry in solved(printed)] == [None] * len(solved(printed))
    assert line in union_of(printed).get(INT_EQUAL_NUMBERS_FILE, []), union_of(printed)


# make-up-an-int-key-for-an-int-keyed-dict: a `dict[int, X]` holding a str key makes up no key, but
# the solver may still add an int key a fork names, which a tracked bool may equal, so the bool
# turns the dict plain whatever keys it holds, and no answer leaves the plan
@pytest.mark.parametrize(
    ("function", "seed"),
    [
        ("str_keyed_tracked_bool", {"b": False, "d": {"a": 1}}),
        ("tracked_bool_then_named", {"b": True, "d": {"a": 1}}),
    ],
)
def test_a_tracked_bool_turns_an_int_annotated_dict_plain_whatever_it_holds(
    function: str, seed: dict[str, object]
) -> None:
    result = run_pyct(f"{INT_EQUAL_NUMBERS}::{function}", json.dumps(seed), *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    printed = input_lines(result.stdout)
    assert downgrade_names(printed[0]) == ["__contains__"], printed[0]
    assert listed(printed[0]) == [], listed(printed[0])
    assert [entry["mismatch_at"] for entry in solved(printed)] == [None] * len(solved(printed))


# make-up-an-int-key-for-an-int-keyed-dict: a merge that turns the dict plain turns what it
# builds plain too, so no fork reads a merged dict an added int key could change unseen
@pytest.mark.parametrize("function", ["merged_fraction", "merged_fraction_first"])
def test_a_merge_with_a_key_pyct_does_not_follow_builds_a_plain_dict(function: str) -> None:
    result = run_pyct(f"{INT_EQUAL_NUMBERS}::{function}", '{"d": {}}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    printed = input_lines(result.stdout)
    assert listed(printed[0]) == [], listed(printed[0])
    assert [entry["mismatch_at"] for entry in solved(printed)] == [None] * len(solved(printed))
