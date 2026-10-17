"""Acceptance tests for part A of match-pyct-v1-on-the-measured-functions: a fixed-count unpack.

Each test spawns ``python -P -m pyct`` through the harness: the count of a split's list is
followed only if the fork the unpack records reaches the solver and the solver's answer, run by
plain Python, unpacks.
"""

import json
from collections.abc import Callable
from functools import partial
from pathlib import Path
from typing import Any

import pytest

from targets.strs import other_unpacks, split_unpacks
from tests.acceptance.harness import REPO_ROOT, input_lines, run_pyct, summary_line
from tests.acceptance.test_lists import args_of, failure_detail, fork_line, listed, solved

UNPACKS = "targets.strs.split_unpacks"
UNPACKS_FILE = str(REPO_ROOT / "targets" / "strs" / "split_unpacks.py")
OTHERS = "targets.strs.other_unpacks"
OTHERS_FILE = str(REPO_ROOT / "targets" / "strs" / "other_unpacks.py")
# what plain Python is given for the unpacks of a value that is not a pair, typed as written
FIVE: Any = 5
ONE_ITEM: Any = [1]


def line_of(text: str, file: str = UNPACKS_FILE, after: str = "") -> int:
    """The line of a fixture that holds ``text``, the first after the line that holds
    ``after``, counted from 1."""
    lines = Path(file).read_text().splitlines()
    start = next(number for number, line in enumerate(lines, 1) if after in line)
    return next(number for number, line in enumerate(lines, 1) if number >= start and text in line)


def covers(line: dict[str, object], number: int, file: str = UNPACKS_FILE) -> bool:
    covered = line["covered"]
    assert isinstance(covered, dict), line
    return number in covered.get(file, [])


def run_covers(stdout: str, number: int, file: str = UNPACKS_FILE) -> bool:
    covered = summary_line(stdout)["covered"]
    assert isinstance(covered, dict), stdout
    return number in covered.get(file, [])


def raised_by_python(call: Callable[[], object]) -> str | None:
    """What plain Python raises for ``call`` in this run, as pyct reports a raise, or None."""
    try:
        call()
    except Exception as error:  # noqa: BLE001 - any raise is the answer
        return f"{type(error).__name__}: {error}"
    return None


def count(op: str, form: list[object], number: int) -> list[object]:
    return [op, ["len", form], number]


# match-pyct-v1-on-the-measured-functions-unpack-flips-a-split-s-count
def test_flips_a_split_s_count() -> None:
    result = run_pyct(f"{UNPACKS}::parse", '{"line": "port"}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of('key, value = line.split("=", 1)')
    fork = count("==", ["split", "line", "'='", 1], 2)
    assert failure_detail(lines[0]) == raised_by_python(lambda: split_unpacks.parse("port"))
    assert listed(lines[0]) == [(at, fork, False)]
    assert fork_line(result.stderr, UNPACKS_FILE, at, "len(line.split('=', 1)) == 2", False)
    after = line_of('if key == "port":')
    unpacked = [
        line for line in solved(lines) if "=" in str(args_of(line)["line"]) and covers(line, after)
    ]
    assert unpacked, lines
    assert run_covers(result.stdout, line_of("return 1"))
    assert run_covers(result.stdout, line_of("return 2"))


# match-pyct-v1-on-the-measured-functions-unpack-flips-too-many-pieces
def test_flips_too_many_pieces() -> None:
    result = run_pyct(f"{UNPACKS}::two", '{"s": "p,q,r"}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of('a, b = s.split(",")')
    fork = count("==", ["split", "s", "','"], 2)
    assert failure_detail(lines[0]) == raised_by_python(lambda: split_unpacks.two("p,q,r"))
    assert listed(lines[0]) == [(at, fork, False)]
    assert fork_line(result.stderr, UNPACKS_FILE, at, "len(s.split(',')) == 2", False)
    after = line_of('if a == "x":')
    unpacked = [
        line
        for line in solved(lines)
        if str(args_of(line)["s"]).count(",") == 1 and covers(line, after)
    ]
    assert unpacked, lines


# match-pyct-v1-on-the-measured-functions-unpack-with-a-star
def test_with_a_star() -> None:
    result = run_pyct(f"{UNPACKS}::starred", '{"s": "p"}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of("first, second, *rest = s.split")
    fork = count(">=", ["split", "s", "','"], 2)
    assert failure_detail(lines[0]) == raised_by_python(lambda: split_unpacks.starred("p"))
    assert listed(lines[0]) == [(at, fork, False)]
    assert fork_line(result.stderr, UNPACKS_FILE, at, "len(s.split(',')) >= 2", False)
    returned = line_of("return first")
    assert any(covers(line, returned) for line in solved(lines)), lines


# a list display as the target counts as a tuple does
def test_a_list_target_counts_too() -> None:
    result = run_pyct(f"{UNPACKS}::into_a_list", '{"s": "p"}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of('[a, b] = s.split(",")')
    assert listed(lines[0]) == [(at, count("==", ["split", "s", "','"], 2), False)]
    assert any(failure_detail(line) is None for line in solved(lines)), lines


# match-pyct-v1-on-the-measured-functions-unpack-keeps-a-decided-count
def test_keeps_a_decided_count() -> None:
    result = run_pyct(f"{UNPACKS}::decided", '{"s": "p,q"}')

    assert result.returncode == 0, result.stderr
    seed = input_lines(result.stdout)[0]
    at = line_of("if len(parts) == 2:")
    # the unpack's own check is a fact, which the line does not list
    assert listed(seed) == [(at, count("==", ["split", "s", "','"], 2), True)]


# match-pyct-v1-on-the-measured-functions-unpack-raises-python-s-error
@pytest.mark.parametrize(
    ("function", "seed", "call"),
    [
        ("five", '{"n": 0}', lambda: split_unpacks.five(0)),
        ("one_item", '{"n": 0}', lambda: split_unpacks.one_item(0)),
        ("two", '{"s": "p"}', lambda: split_unpacks.two("p")),
    ],
)
def test_raises_python_s_error(function: str, seed: str, call: Callable[[], object]) -> None:
    result = run_pyct(f"{UNPACKS}::{function}", seed)

    assert result.returncode == 0, result.stderr
    first = input_lines(result.stdout)[0]
    expected = raised_by_python(call)
    assert expected is not None
    assert failure_detail(first) == expected


# each target's seed, and the forks of each line its run records, in order, as origin/v2 records
# them at 024580ff (the forks are those of 8e317e87: parts C and D changed no fork)
OTHER_FORKS: dict[str, tuple[dict[str, object], list[list[tuple[object, object, object]]]]] = {
    "plain_tuple": ({"n": 0}, [[(12, [">", "n", 5], False)], [(12, [">", "n", 5], True)]]),
    "plain_list": ({"n": 0}, [[(20, ["==", "n", 2], False)], [(20, ["==", "n", 2], True)]]),
    "generator": (
        {"n": 0},
        [[(27, [">", ["*", "n", 2], 10], False)], [(27, [">", ["*", "n", 2], 10], True)]],
    ),
    "returned": (
        {"n": 0},
        [[(34, ["==", ["+", "n", 1], 7], False)], [(34, ["==", ["+", "n", 1], 7], True)]],
    ),
    "tracked_list": (
        {"xs": [1, 2]},
        [
            [
                (40, [">", ["len", "xs"], 0], True),
                (40, [">", ["len", "xs"], 1], True),
                (40, [">", ["len", "xs"], 2], False),
                (41, [">", ["[]", "xs", 0], ["[]", "xs", 1]], taken),
            ]
            for taken in (False, True)
        ],
    ),
    "tracked_str": (
        {"s": "ab"},
        [
            [
                (47, [">", ["len", "s"], 0], True),
                (47, [">", ["len", "s"], 1], True),
                (47, [">", ["len", "s"], 2], False),
                (48, ["==", ["[]", "s", 0], "'q'"], taken),
            ]
            for taken in (False, True)
        ],
    ),
    "swap": ({"n": 0, "m": 1}, [[(56, [">", "m", "n"], True)], [(56, [">", "m", "n"], False)]]),
}
_PIECES = [["split", ["[]", ["split", "s", "';'"], at], "'='"] for at in (0, 1)]
OTHER_FORKS["split_in_a_loop"] = (
    {"s": "a=b;c=d"},
    [
        [(64, ["==", ["[]", piece, 0], ["[]", piece, 1]], taken) for piece, taken in sides]
        for sides in (
            zip(_PIECES, (False, False), strict=True),
            zip(_PIECES, (False, True), strict=True),
        )
    ],
)


# match-pyct-v1-on-the-measured-functions-unpack-leaves-other-values-as-they-were
@pytest.mark.parametrize("function", OTHER_FORKS)
def test_leaves_other_values_as_they_were(function: str) -> None:
    seed, expected = OTHER_FORKS[function]
    result = run_pyct(f"{OTHERS}::{function}", json.dumps(seed))

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert [listed(line) for line in lines] == expected
    target = getattr(other_unpacks, function)
    for line in lines:
        args = args_of(line)
        assert failure_detail(line) == raised_by_python(partial(target, **args)), line
