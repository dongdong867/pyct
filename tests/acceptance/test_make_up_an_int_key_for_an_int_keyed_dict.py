"""Acceptance tests for make-up-an-int-key-for-an-int-keyed-dict.

A dict annotated ``dict[int, X]`` whose keys are all ints, an empty one included, meets a count
with made-up int keys: the smallest non-negative ints it does not hold and no fork names. A
line writes each as JSON text, and ``--args`` reads it back as the int.
"""

import json
import re

import pytest

from tests.acceptance.harness import REPO_ROOT, input_lines, run_pyct, summary_line
from tests.acceptance.test_dicts import UNTIL_NO_GAIN, dict_of
from tests.acceptance.test_lists import args_of, covered_of, listed, number, solved

DICTS = REPO_ROOT / "targets" / "dicts"
MADE_UP_INTS = "targets.dicts.made_up_ints"
MADE_UP_INTS_FILE = str(DICTS / "made_up_ints.py")
INT_ONLY = "targets.dicts.settled::int_only"
SETTLED_FILE = str(DICTS / "settled.py")
ACCEPTED = REPO_ROOT / "tools" / "compare_coverage" / "accepted-per-merge.jsonl"

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


# make-up-an-int-key-for-an-int-keyed-dict-reaches-the-int-only-line
@pytest.mark.xfail(
    strict=True,
    reason="needs-info: every answer that drops key 1 flips the lookup a walk's shared key 1 "
    "recorded given its place, which leaves the plan and is an `unknown` miss",
)
def test_reaches_the_int_only_line() -> None:
    result = run_pyct(INT_ONLY, '{"d": {"1": 9}}', "--plateau", "5")

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    reached = [line for line in lines if 12 in covered_of([line]).get(SETTLED_FILE, [])]
    assert reached, covered_of(lines)
    for line in reached:
        d = int_keyed(line)
        # the path Python takes for this `d`: some value above 5 and no key 1
        assert 1 not in d and any(number(v) > 5 for v in d.values()), d
    rows = [json.loads(row) for row in ACCEPTED.read_text().splitlines()[1:]]
    assert INT_ONLY not in [row["target"] for row in rows]


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
    covering = [line for line in lines if 23 in covered_of([line]).get(MADE_UP_INTS_FILE, [])]
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
    seed = input_lines(str_keyed.stdout)[0]
    assert (3, [">", ["len", "d"], 1], False) in listed(seed), listed(seed)
    misses = summary_line(str_keyed.stdout)["misses"]
    assert isinstance(misses, list)
    assert (3, "unsat") in {(miss["line"], miss["why"]) for miss in misses}, misses
    assert any(
        entry.startswith(f"missed {MADE_UP_INTS_FILE}:3:") and entry.endswith(" unsat")
        for entry in str_keyed.stderr.splitlines()
    ), str_keyed.stderr
