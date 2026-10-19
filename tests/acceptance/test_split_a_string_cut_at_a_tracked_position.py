"""Acceptance tests for split-a-string-cut-at-a-tracked-position: a split v2 has no one formula
for, built from find and slice steps, one fork per step.

Each test spawns ``python -P -m pyct`` through the harness, so a step's fork counts only if it
reaches the solver and the solver's answer, run by plain Python, takes the path aimed at.
"""

import json
import time
from collections.abc import Callable
from functools import partial
from pathlib import Path

import pytest

from targets.strs import split_steps
from tests.acceptance.harness import REPO_ROOT, input_lines, run_pyct, summary_line
from tests.acceptance.test_lists import args_of, failure_detail, fork_line, listed, solved

STEPS = "targets.strs.split_steps"
STEPS_FILE = str(REPO_ROOT / "targets" / "strs" / "split_steps.py")
MSC = "targets.strs.msc_version"
MSC_FILE = str(REPO_ROOT / "targets" / "strs" / "msc_version.py")
# the lines of the copied function only PyCT v1 covered, as the 2026-10-17 evaluation measured
V1_ONLY = (8, 9, 10, 11, 13, 15, 17, 18, 19, 20, 22, 23, 24, 28)


def line_of(text: str, after: str = "", file: str = STEPS_FILE) -> int:
    """The line of a fixture that holds ``text``, the first after the line that holds
    ``after``, counted from 1."""
    lines = Path(file).read_text().splitlines()
    start = next(number for number, line in enumerate(lines, 1) if after in line)
    return next(number for number, line in enumerate(lines, 1) if number >= start and text in line)


def covers(line: dict[str, object], number: int, file: str = STEPS_FILE) -> bool:
    covered = line["covered"]
    assert isinstance(covered, dict), line
    return number in covered.get(file, [])


def raised_by_python(call: Callable[[], object]) -> str | None:
    """What plain Python raises for ``call`` in this run, as pyct reports a raise, or None."""
    try:
        call()
    except Exception as error:  # noqa: BLE001 - any raise is the answer
        return f"{type(error).__name__}: {error}"
    return None


def downgrade_names(line: dict[str, object]) -> list[str]:
    downgrades = line["downgrades"]
    assert isinstance(downgrades, list), line
    return [str(entry["name"]) for entry in downgrades]


def lines_at(line: dict[str, object], number: int) -> list[tuple[object, object, object]]:
    """The forks a line recorded at one line of the fixture."""
    return [fork for fork in listed(line) if fork[0] == number]


def each_ends_as_python(lines: list[dict[str, object]], function: Callable[..., object]) -> None:
    """Every input's line ends as plain Python ends on its arguments: returned, or the same
    raise."""
    for line in lines:
        args = args_of(line)
        assert failure_detail(line) == raised_by_python(partial(function, **args)), line


# split-a-string-cut-at-a-tracked-position-flips-a-cut-split-s-count
def test_flips_a_cut_split_s_count() -> None:
    result = run_pyct(f"{STEPS}::cut_count", '{"version": "a,b", "i": 0}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    at = line_of('parts = version[i:].split(",")')
    assert lines_at(lines[0], at), lines[0]
    returned = line_of("return 1", after="def cut_count")
    three = [
        line
        for line in solved(lines)
        if str(args_of(line)["version"])[int(str(args_of(line)["i"])) :].count(",") == 2
        and covers(line, returned)
    ]
    assert three, lines


# split-a-string-cut-at-a-tracked-position-covers-get-build-version
@pytest.mark.serial
def test_covers_get_build_version() -> None:
    result = run_pyct(f"{MSC}::get_build_version", '{"version": ""}', "--budget", "30", timeout=90)

    assert result.returncode == 0, result.stderr
    summary = summary_line(result.stdout)
    covered, uncovered = summary["covered"], summary["uncovered"]
    assert isinstance(covered, dict) and isinstance(uncovered, dict), summary
    # every line PyCT v1 covered; 26 and 30 no input reaches, and coverage counts no line 30,
    # which follows a return on every path
    assert set(covered[MSC_FILE]) >= {1, 2, 3, 4, 5, 6, 7, *V1_ONLY}, summary
    assert set(uncovered.get(MSC_FILE, [])) <= {26, 30}, summary


# split-a-string-cut-at-a-tracked-position-follows-a-tracked-separator
def test_follows_a_tracked_separator() -> None:
    result = run_pyct(f"{STEPS}::by_a_separator", '{"s": "a,b", "d": ","}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert all("split" not in downgrade_names(line) for line in lines), lines
    after = "def by_a_separator"
    assert any(covers(line, line_of("return 1", after)) for line in lines), lines
    assert any(covers(line, line_of("return 2", after)) for line in lines), lines


# split-a-string-cut-at-a-tracked-position-follows-a-tracked-limit
def test_follows_a_tracked_limit() -> None:
    result = run_pyct(f"{STEPS}::by_a_limit", '{"s": "a,b,c,d", "n": 0}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert all("split" not in downgrade_names(line) for line in lines), lines
    returned = line_of("return 1", after="def by_a_limit")
    assert any(covers(line, returned) for line in solved(lines)), lines


# split-a-string-cut-at-a-tracked-position-follows-an-int-s-text
@pytest.mark.parametrize(
    ("function", "seed"),
    [("int_text", '{"n": 5}'), ("joined_text", '{"s": "a", "n": 5}')],
)
def test_follows_an_int_s_text(function: str, seed: str) -> None:
    result = run_pyct(f"{STEPS}::{function}", seed)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    returned = line_of("return 1", after=f"def {function}")
    assert any(covers(line, returned) for line in solved(lines)), lines


# split-a-string-cut-at-a-tracked-position-splits-whitespace-as-python
@pytest.mark.parametrize("n", [-1, 0, 1])
@pytest.mark.parametrize("s", ["a\tb\nc", " a\u3000x ", "a\x1cx", "  a  b\t\n", "\u2028a x\xa0"])
def test_splits_whitespace_as_python(s: str, n: int) -> None:
    seed = json.dumps({"s": s, "i": 0, "n": n})
    result = run_pyct(f"{STEPS}::by_whitespace", seed)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    each_ends_as_python(lines, split_steps.by_whitespace)


# split-a-string-cut-at-a-tracked-position-splits-whitespace-as-python
def test_splits_whitespace_to_a_word() -> None:
    result = run_pyct(f"{STEPS}::by_whitespace", '{"s": "a\\tb\\nc", "i": 0, "n": -1}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    returned = line_of("return 1", after="def by_whitespace")
    assert any(covers(line, returned) for line in solved(lines)), lines


# split-a-string-cut-at-a-tracked-position-rsplits-as-python
@pytest.mark.parametrize("n", [-1, 0, 1, 5, True])
@pytest.mark.parametrize(("s", "d"), [("aaa", "aa"), ("a,b,,c", ","), ("xaxax", "xax")])
def test_rsplits_as_python(s: str, d: str, n: int) -> None:
    result = run_pyct(f"{STEPS}::from_the_right", json.dumps({"s": s, "i": 0, "d": d, "n": n}))

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    assert all("rsplit" not in downgrade_names(line) for line in lines), lines
    each_ends_as_python(lines, split_steps.from_the_right)


# split-a-string-cut-at-a-tracked-position-rsplits-as-python, by whitespace
@pytest.mark.parametrize("n", [-1, 0, 1, 5])
@pytest.mark.parametrize("s", [" a\tb  c ", "a\u3000b", "   "])
def test_rsplits_whitespace_as_python(s: str, n: int) -> None:
    result = run_pyct(
        f"{STEPS}::by_whitespace_from_the_right", json.dumps({"s": s, "i": 0, "n": n})
    )

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    each_ends_as_python(lines, split_steps.by_whitespace_from_the_right)


# split-a-string-cut-at-a-tracked-position-rsplits-as-python: three words from the right are
# asked within the solver's limit (review of PR #148: the walk back reversed each prefix apart
# and ran to the limit)
def test_rsplits_three_words_within_the_limit() -> None:
    result = run_pyct(f"{STEPS}::three_words_from_the_right", '{"s": "a", "i": 0}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    returned = line_of("return 1", after="def three_words_from_the_right")
    assert any(covers(line, returned) for line in solved(lines)), lines
    solver = summary_line(result.stdout)["solver"]
    assert isinstance(solver, dict) and solver["timeout"] == 0, solver


# split-a-string-cut-at-a-tracked-position-forks-whatever-the-list-meets
def test_forks_whatever_the_list_meets() -> None:
    result = run_pyct(f"{STEPS}::counted_by_a_loop", '{"version": "a", "i": 0}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    returned = line_of("return 1", after="def counted_by_a_loop")
    assert any(covers(line, returned) for line in solved(lines)), lines


# split-a-string-cut-at-a-tracked-position-reads-a-piece-at-a-tracked-index
def test_reads_a_piece_at_a_tracked_index() -> None:
    result = run_pyct(f"{STEPS}::piece_at_an_index", '{"s": "x;y", "i": 0}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    expected = raised_by_python(lambda: split_steps.piece_at_an_index("x;y", 0))
    assert expected is not None
    assert failure_detail(lines[0]) == expected
    assert lines_at(lines[0], line_of('a, b = first.split(",")')), lines[0]
    returned = line_of("return a", after="def piece_at_an_index")
    assert any(covers(line, returned) for line in solved(lines)), lines


# split-a-string-cut-at-a-tracked-position-keeps-one-formula-splits
def test_keeps_one_formula_splits() -> None:
    # each run's forks as origin/v2 38a7000c recorded them, captured from 9d50ce2d, which
    # changed no split
    recorded = json.loads((Path(__file__).parent / "one_formula_splits.json").read_text())
    for run in recorded:
        result = run_pyct(run["target"], json.dumps(run["seed"]))

        assert result.returncode == 0, result.stderr
        forks = [[list(fork) for fork in listed(line)] for line in input_lines(result.stdout)]
        assert forks == run["forks"], run["target"]


# split-a-string-cut-at-a-tracked-position-bounds-the-forks-of-a-long-split
@pytest.mark.serial
def test_bounds_the_forks_of_a_long_split() -> None:
    s = ",".join(["a"] * 501)
    started = time.monotonic()
    result = run_pyct(f"{STEPS}::long_cut", json.dumps({"s": s, "i": 0}), "--budget", "10")
    tracked = time.monotonic() - started
    started = time.monotonic()
    plain = run_pyct(f"{STEPS}::long_plain_cut", json.dumps({"s": s}), "--budget", "10")
    untracked = time.monotonic() - started

    assert result.returncode == 0, result.stderr
    assert plain.returncode == 0, plain.stderr
    seed = input_lines(result.stdout)[0]
    assert failure_detail(seed) is None, seed
    at = line_of('parts = s[i:].split(",")')
    # one fork a piece, 501 pieces, and none past them
    assert len(lines_at(seed, at)) <= 501 + 2, len(lines_at(seed, at))
    print(f"long split: {tracked:.1f} s at a tracked bound, {untracked:.1f} s at a plain one")


# split-a-string-cut-at-a-tracked-position-raises-on-an-empty-separator
def test_raises_on_an_empty_separator() -> None:
    # the run covers every line before it asks for an empty separator, which only raises, so it
    # goes past full coverage, as a run looking for failures does
    result = run_pyct(
        f"{STEPS}::by_a_separator", '{"s": "a,b", "d": ","}', "--goal", "bugs", "--budget", "5"
    )

    assert result.returncode == 0, result.stderr
    expected = raised_by_python(lambda: split_steps.by_a_separator("a,b", ""))
    assert expected is not None
    empty = [line for line in solved(input_lines(result.stdout)) if args_of(line)["d"] == ""]
    assert empty, result.stdout
    assert all(failure_detail(line) == expected for line in empty), empty


# split-a-string-cut-at-a-tracked-position-raises-on-an-empty-separator
def test_raises_on_an_empty_separator_from_the_seed() -> None:
    result = run_pyct(f"{STEPS}::by_a_separator", '{"s": "a,b", "d": ""}')

    assert result.returncode == 0, result.stderr
    seed = input_lines(result.stdout)[0]
    expected = raised_by_python(lambda: split_steps.by_a_separator("a,b", ""))
    assert failure_detail(seed) == expected
    at = line_of("parts = s.split(d)")
    assert (at, ["!=", "d", "''"], False) in listed(seed), seed
    assert fork_line(result.stderr, STEPS_FILE, at, "d != ''", False)


# split-a-string-cut-at-a-tracked-position-unpack-raises-python-s-error
def test_unpack_raises_python_s_error() -> None:
    result = run_pyct(f"{STEPS}::unpacked_cut", '{"version": "abc", "i": 1}')

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    expected = raised_by_python(lambda: split_steps.unpacked_cut("abc", 1))
    assert expected is not None
    assert failure_detail(lines[0]) == expected
    at = line_of('s, rest = version[i:].split(" ", 1)')
    assert lines_at(lines[0], at), lines[0]
    returned = line_of("return s", after="def unpacked_cut")
    spaced = [
        line
        for line in solved(lines)
        if " " in str(args_of(line)["version"])[int(str(args_of(line)["i"])) :]
        and covers(line, returned)
    ]
    assert spaced, lines


# split-a-string-cut-at-a-tracked-position-refuses-a-limit-python-refuses
@pytest.mark.parametrize(
    ("function", "seed", "call"),
    [
        ("limit_of_text", '{"s": "a,b", "t": "1"}', lambda: split_steps.limit_of_text("a,b", "1")),
        (
            "limit_of_a_float",
            '{"s": "a,b", "i": 0}',
            lambda: split_steps.limit_of_a_float("a,b", 0),
        ),
    ],
)
def test_refuses_a_limit_python_refuses(
    function: str, seed: str, call: Callable[[], object]
) -> None:
    result = run_pyct(f"{STEPS}::{function}", seed)

    assert result.returncode == 0, result.stderr
    expected = raised_by_python(call)
    assert expected is not None and expected.startswith("TypeError"), expected
    for line in input_lines(result.stdout):
        assert failure_detail(line) == expected, line
