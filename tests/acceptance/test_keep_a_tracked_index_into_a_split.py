"""Acceptance tests for keep-a-tracked-index-into-a-split-as-v2-does: a tracked index into a
split's list reads the piece Python reads, as origin/v2's plain list of pieces hands it out, so
the piece keeps its condition and a flip of its compare is answered."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from tests.acceptance.harness import REPO_ROOT, input_lines, run_pyct
from tests.acceptance.test_follow_the_length_of_a_split import covers, line_of
from tests.acceptance.test_lists import UNTIL_NO_GAIN, args_of, downgrade_names, solved

INDEXES = "targets.strs.split_indexes"
INDEXES_FILE = str(REPO_ROOT / "targets" / "strs" / "split_indexes.py")


def _wrapped(s: Any, n: Any) -> bool:
    parts = s.split(",")
    return parts[n % len(parts)] == "z"


def _at(s: Any, n: Any) -> bool:
    parts = s.split(",")
    return 0 <= n < len(parts) and parts[n] == "z"


def _from_the_end(s: Any, n: Any) -> bool:
    parts = s.split(",")
    return 0 < n <= len(parts) and parts[-n] == "z"


def _counted_back(s: Any, n: Any) -> bool:
    parts = s.split(",")
    return 0 < n <= len(parts) and parts[len(parts) - n] == "z"


@pytest.mark.parametrize(
    ("target", "agrees"),
    [
        ("wrapped", _wrapped),
        ("at_a_tracked_index", _at),
        ("from_the_end", _from_the_end),
        ("counted_back", _counted_back),
    ],
    ids=["n % len", "n", "-n", "len - n"],
)
def test_reads_a_split_at_a_tracked_index_as_python_does(
    target: str, agrees: Callable[..., bool]
) -> None:
    result = run_pyct(f"{INDEXES}::{target}", '{"s": "a,b", "n": 3}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    # the piece Python reads keeps its condition, and no loss is named, as on origin/v2
    assert all("__getitem__" not in downgrade_names(line) for line in lines), lines
    returned = _return_of(target)
    reached = [args_of(line) for line in solved(lines) if covers(line, returned, INDEXES_FILE)]
    assert reached and all(agrees(**args) for args in reached), lines


def _return_of(target: str) -> int:
    """The line of ``return 1`` in the fixture's ``target``."""
    start = line_of(f"def {target}(", INDEXES_FILE)
    lines = Path(INDEXES_FILE).read_text().splitlines()
    return next(at for at in range(start, len(lines) + 1) if lines[at - 1] == "        return 1")


# a fork on a piece a tracked index handed out holds only while the index has the value it
# had: a later flip of the count moves the index, as plain Python would
def test_flips_the_count_after_a_piece_read_at_a_tracked_index() -> None:
    result = run_pyct(f"{INDEXES}::counted_after_an_index", '{"s": "a,b", "n": 1}', *UNTIL_NO_GAIN)

    assert result.returncode == 0, result.stderr
    lines = input_lines(result.stdout)
    one = line_of('return "one piece"', INDEXES_FILE)
    reached = [args_of(line) for line in solved(lines) if covers(line, one, INDEXES_FILE)]
    assert reached, lines
    for args in reached:
        s, n = args["s"], args["n"]
        assert isinstance(s, str) and isinstance(n, int), args
        parts = s.split(",")
        assert len(parts) == 1 and 0 <= n < 1 and parts[n] != "z", args
