"""Acceptance tests for let-the-solver-choose-a-small-dict-s-walk-key, the happy path and the edges.

The target's own walk of a small unchanged dict hands out a walk key, `["key", "d", i]`, the key
the walk reads at pass i. When the ask with each walk key where the input had it is unsat, pyct
asks again with the key at each pass a fork names left to the solver, and an answer lists the
chosen keys first. Each test runs pyct through the command line, as a person or sweep reads it.
"""

import json
from collections.abc import Callable

import pytest

from targets.dicts import settled, walk_keys
from tests.acceptance.harness import (
    REPO_ROOT,
    first_line,
    forks_of,
    input_lines,
    lines_expressions_and_sides,
    run_pyct,
    summary_line,
)
from tests.acceptance.test_dicts import dict_of
from tests.acceptance.test_lists import number, solved
from tests.acceptance.test_make_up_an_int_key_for_an_int_keyed_dict import int_keyed
from tests.acceptance.test_pass_keywords_through_a_downgrade import covered_in

SETTLED = "targets.dicts.settled"
W = "targets.dicts.walk_keys"
F = str(REPO_ROOT / "targets" / "dicts" / "settled.py")
WF = str(REPO_ROOT / "targets" / "dicts" / "walk_keys.py")
FIVE = ("--budget", "5")


def ints(count: int, value: int) -> str:
    """An N-key int seed: `{"d": {"1": v, ..., "N": v}}`."""
    return json.dumps({"d": {str(key): value for key in range(1, count + 1)}})


def walk_keyed(line: dict[str, object]) -> bool:
    """Whether a line's forks name a walk key."""
    return '["key"' in json.dumps(line["forks"])


def covered(lines: list[dict[str, object]], file: str) -> set[int]:
    return {number for line in lines for number in covered_in(line, file)}


def cut(line: dict[str, object]) -> bool:
    """Whether the run's deadline ended the input, so its forks stop short of its aim."""
    failure = line.get("failure")
    return isinstance(failure, dict) and failure.get("detail") == "deadline passed"


def reached(lines: list[dict[str, object]]) -> None:
    """Every solver line the deadline did not cut reaches its aim."""
    finished = [line for line in solved(lines) if not cut(line)]
    assert [line["mismatch_at"] for line in finished] == [None] * len(finished)


def first_key(line: dict[str, object]) -> object:
    return next(iter(dict_of(line, "d")), None)


def blocks(stderr: str) -> list[list[tuple[str, str]]]:
    """Each input's forks as stderr prints them, a seed's or a solver's line opening each: the
    text and the side."""
    found: list[list[tuple[str, str]]] = []
    for row in stderr.splitlines():
        if row.startswith(("seed ", "solver ")):
            found.append([])
        elif row.startswith("fork ") and found:
            _, text, side = row.removeprefix("fork ").split("  ")
            found[-1].append((text, side))
    return found


# let-the-solver-choose-a-small-dict-s-walk-key-reaches-the-int-only-line
def test_reaches_the_int_only_line() -> None:
    result = run_pyct(f"{SETTLED}::int_only", '{"d": {"1": 9}}', *FIVE)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert 12 in covered(lines, F)
    found = [int_keyed(line) for line in lines if 12 in covered_in(line, F)]
    assert any(list(d)[0] != 1 and number(d[list(d)[0]]) > 5 and 1 not in d for d in found), found
    reached(lines)
    misses = summary_line(result.stdout)["misses"]
    assert isinstance(misses, list)
    assert (10, 11, "unknown") not in {(m["line"], m["col"], m["why"]) for m in misses}


@pytest.mark.parametrize(
    ("target", "file", "line"),
    [(f"{SETTLED}::int_only", F, 12), (f"{W}::int_below", WF, 9)],
    ids=["from-a-low-value", "under-a-low-bound"],
)
# let-the-solver-choose-a-small-dict-s-walk-key-reaches-the-line-from-a-low-value
# let-the-solver-choose-a-small-dict-s-walk-key-reaches-the-line-under-a-low-bound
def test_reaches_the_line_from_a_low_seed(target: str, file: str, line: int) -> None:
    result = run_pyct(target, '{"d": {"1": 0}}', *FIVE)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert line in covered(lines, file)
    reached(lines)


# let-the-solver-choose-a-small-dict-s-walk-key-prints-the-key-by-its-pass
def test_prints_the_key_by_its_pass() -> None:
    result = run_pyct(f"{SETTLED}::int_only", '{"d": {"1": 9}}', *FIVE)

    assert result.returncode == 0, result.stderr
    seed = first_line(result.stdout)
    assert (10, [">", ["[]", "d", ["key", "d", 0]], 5], True) in lines_expressions_and_sides(seed)
    assert {"line": 11, "col": 15, "taken": True, "expression": ["in", 1, "d"]} in [
        {key: fork[key] for key in ("line", "col", "taken", "expression")}
        for fork in forks_of(seed)
    ]
    printed = blocks(result.stderr)
    assert ("d[list(d)[0]] > 5", "taken") in printed[0]
    for line, forks in zip(input_lines(result.stdout), printed, strict=True):
        d = int_keyed(line)
        for text, side in forks:
            assert eval(text, {"d": d}) is (side == "taken"), (text, side, d)  # noqa: S307


@pytest.mark.parametrize(
    ("target", "seed", "function"),
    [
        (f"{SETTLED}::int_only", '{"d": {"1": 9}}', settled.int_only),
        (f"{SETTLED}::int_only", '{"d": {"1": 0}}', settled.int_only),
        (f"{W}::int_below", '{"d": {"1": 0}}', walk_keys.int_below),
    ],
    ids=["int-only", "low-value", "low-bound"],
)
# let-the-solver-choose-a-small-dict-s-walk-key-lists-the-chosen-keys-first
def test_lists_the_chosen_keys_first(target: str, seed: str, function: Callable[..., int]) -> None:
    result = run_pyct(target, seed, *FIVE)

    assert result.returncode == 0, result.stderr
    lines = solved(input_lines(result.stdout))
    moved = [line for line in lines if first_key(line) not in (None, "1")]
    assert moved, result.stdout
    for line in moved[:3]:
        again = run_pyct(target, "--args", json.dumps(line["args"]), "--budget", "0.5")
        assert again.returncode == 0, again.stderr
        assert lines_expressions_and_sides(first_line(again.stdout)) == (
            lines_expressions_and_sides(line)
        )
        returned = function(int_keyed(line))
        file = F if target.startswith(SETTLED) else WF
        one = 12 if target.startswith(SETTLED) else 9
        assert (returned == 1) is (one in covered_in(line, file)), line


# let-the-solver-choose-a-small-dict-s-walk-key-chooses-at-200-keys
def test_chooses_at_200_keys() -> None:
    result = run_pyct(f"{SETTLED}::int_only", ints(200, 9), "--budget", "10")

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert 12 in covered(lines, F)
    reached(lines)


# let-the-solver-choose-a-small-dict-s-walk-key-keeps-today-s-keys-past-200
def test_keeps_today_s_keys_past_200() -> None:
    result = run_pyct(f"{SETTLED}::int_only", ints(201, 9), "--budget", "10")

    # the walk still hands out walk keys, so an answer that grows a dict past 200 walks it as
    # the path did; the solver chooses none of them past 200 (review of PR #138)
    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert walk_keyed(lines[0])
    assert all(first_key(line) == "1" for line in solved(lines)), lines
    assert 12 not in covered(lines, F)
    reached(lines)


@pytest.mark.parametrize(
    ("target", "seed", "line", "key"),
    [
        (f"{SETTLED}::only_a", '{"d": {"a": 9}}', 4, "a"),
        (f"{W}::ab_only", '{"d": {"ab": 9}}', 16, "ab"),
    ],
    ids=["shared", "copied"],
)
# let-the-solver-choose-a-small-dict-s-walk-key-chooses-a-str-key-python-shares
# let-the-solver-choose-a-small-dict-s-walk-key-chooses-a-copied-str-key
def test_chooses_a_str_key(target: str, seed: str, line: int, key: str) -> None:
    result = run_pyct(target, seed, *FIVE)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    file = F if target.startswith(SETTLED) else WF
    reaching = [found for found in solved(lines) if line in covered_in(found, file)]
    assert any(key not in dict_of(found, "d") for found in reaching), reaching
    reached(lines)


# let-the-solver-choose-a-small-dict-s-walk-key-chooses-a-made-up-key-beside-a-count
def test_chooses_a_made_up_key_beside_a_count() -> None:
    result = run_pyct(f"{W}::first_of_two", '{"d": {"ab": 9}}', *FIVE)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    reaching = [dict_of(found, "d") for found in solved(lines) if 24 in covered_in(found, WF)]

    def meets(d: dict[str, object]) -> bool:
        keys = list(d)
        first = d[keys[0]] if keys else 0
        made = [key for key in keys if key.startswith("pyct")]
        return len(d) == 2 and "ab" not in d and isinstance(first, int) and first > 5 and bool(made)

    assert any(meets(d) for d in reaching), reaching
    reached(lines)


# let-the-solver-choose-a-small-dict-s-walk-key-compares-a-chosen-key
def test_compares_a_chosen_key() -> None:
    result = run_pyct(f"{W}::named", '{"d": {"x": 9}}', *FIVE)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert (31, ["==", ["key", "d", 0], "'admin'"], False) in lines_expressions_and_sides(lines[0])
    assert any(first_key(line) == "admin" and 32 in covered_in(line, WF) for line in solved(lines))


@pytest.mark.parametrize(
    ("function", "seed", "forks"),
    [
        (
            "stored_first",
            '{"d": {"a": 9}}',
            [
                (37, ["in", "'zz'", "d"], False),
                (39, ["in", "'a'", "d"], True),
                (39, [">", ["[]", "d", "'a'"], 5], True),
                (38, [">", ["+", ["len", "d"], 1], 2], False),
            ],
        ),
        (
            "marked_first",
            '{"n": "pyct1", "d": {"a": 9}}',
            [
                (45, ["in", "n", "d"], False),
                (46, [">", ["+", ["len", "d"], 1], 1], True),
                (46, [">", ["+", ["len", "d"], 1], 2], False),
                (49, ["in", "'a'", "d"], True),
                (49, [">", ["[]", "d", "'a'"], 5], True),
                (49, ["in", "'a'", "d"], True),
            ],
        ),
    ],
    ids=["stored", "marked"],
)
# let-the-solver-choose-a-small-dict-s-walk-key-keeps-a-changed-dict-s-keys
def test_keeps_a_changed_dict_s_keys(function: str, seed: str, forks: list[object]) -> None:
    result = run_pyct(f"{W}::{function}", seed, *FIVE)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert not any(walk_keyed(line) for line in lines)
    # the base's seed line
    assert lines_expressions_and_sides(lines[0]) == forks


def _python_s_walk(line: int, size: int) -> list[object]:
    """A seed line of a walk Python makes, as the base prints it: the walk's passes over one key,
    the lookup of the key it handed out, then the value under it."""
    return [
        (size, [">", ["len", "d"], 0], True),
        (size, [">", ["len", "d"], 1], False),
        (line, ["in", "'a'", "d"], True),
        (line, [">", ["[]", "d", "'a'"], 5], True),
    ]


@pytest.mark.parametrize(
    ("function", "forks"),
    [
        ("sorted_walk", _python_s_walk(56, 55)),
        ("listed_walk", _python_s_walk(63, 62)),
        (
            "reversed_walk",
            [
                (69, [">", ["len", "d"], 0], True),
                (70, ["in", "'a'", "d"], True),
                (70, [">", ["[]", "d", "'a'"], 5], True),
                (69, [">", ["len", "d"], 1], False),
            ],
        ),
        (
            "first_key",
            [
                (76, ["!=", ["len", "d"], 0], True),
                (78, ["in", "'a'", "d"], True),
                (78, [">", ["[]", "d", "'a'"], 5], True),
            ],
        ),
        (
            "copied_walk",
            [
                (84, [">", ["len", "d"], 0], True),
                (84, [">", ["len", "d"], 1], False),
                (84, ["in", "'a'", "d"], True),
                (86, [">", ["[]", "d", "'a'"], 5], True),
            ],
        ),
    ],
)
# let-the-solver-choose-a-small-dict-s-walk-key-keeps-other-walks-as-today
def test_keeps_other_walks_as_today(function: str, forks: list[object]) -> None:
    result = run_pyct(f"{W}::{function}", '{"d": {"a": 9}}', *FIVE)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert not any(walk_keyed(line) for line in lines)
    assert lines_expressions_and_sides(lines[0]) == forks


# let-the-solver-choose-a-small-dict-s-walk-key-fixes-a-key-no-fork-reads
def test_fixes_a_key_no_fork_reads() -> None:
    result = run_pyct(f"{W}::counted", '{"d": {"ab": 9}}', *FIVE)

    assert result.returncode == 0, result.stderr
    assert not any(walk_keyed(line) for line in input_lines(result.stdout))
    misses = summary_line(result.stdout)["misses"]
    assert isinstance(misses, list)
    # the base's misses: none but the one fork the budget may cut
    assert {m["why"] for m in misses} <= {"timeout"}, misses


# let-the-solver-choose-a-small-dict-s-walk-key-walks-an-unchanged-dict-twice-alike
def test_walks_an_unchanged_dict_twice_alike() -> None:
    result = run_pyct(f"{W}::twice", '{"d": {"ab": 9}}', *FIVE)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert (104, [">", ["[]", "d", ["key", "d", 0]], 5], True) in lines_expressions_and_sides(
        lines[0]
    )
    assert 105 in covered(lines, WF)
    reached(lines)
