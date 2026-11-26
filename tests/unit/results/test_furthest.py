"""The way to one missed line, and the input that got furthest along it: what a guess ask sends."""

import textwrap
import time
from pathlib import Path

from pyct.core.foundation.branch import Branch, Site
from pyct.results.causes import Condition
from pyct.results.failure import Failure, FailureKind
from pyct.results.furthest import Way, way_to
from pyct.results.record import InputRecord

WAY = """\
def handle(s, n):
    if n > 10:
        y = 10 // (n - 11)
        if s == "a":
            return y
        return int(s)
    return 0


def other(x):
    if x:
        return 1
    return 2
"""


def module(tmp_path: Path) -> str:
    file = tmp_path / "m.py"
    file.write_text(textwrap.dedent(WAY))
    return str(file)


def fork(file: str, at: tuple[int, int], *, taken: bool, raising: bool = False) -> Branch:
    site = Site(file=file, line=at[0], col=at[1])
    return Branch(expression=["<", "n", 0], taken=taken, site=site, raising=raising)


def small(file: str, n: int) -> InputRecord:
    """An input that took ``n > 10``'s false side."""
    return InputRecord({"s": "b", "n": n}, (fork(file, (2, 7), taken=False),), frozenset({2, 7}))


def divided_by_zero(file: str) -> InputRecord:
    forks = (fork(file, (2, 7), taken=True), fork(file, (3, 12), taken=False, raising=True))
    failure = Failure(FailureKind.TARGET_RAISED, "ZeroDivisionError: integer division by zero")
    return InputRecord({"s": "b", "n": 11}, forks, frozenset({2, 3}), failure)


def equal_to_a(file: str, n: int) -> InputRecord:
    """An input that passed the division and took ``s == "a"``'s true side."""
    forks = (
        fork(file, (2, 7), taken=True),
        fork(file, (3, 12), taken=True, raising=True),
        fork(file, (4, 11), taken=True),
    )
    return InputRecord({"s": "a", "n": n}, forks, frozenset({2, 3, 4, 5}))


def test_the_way_holds_each_condition_with_the_side_the_line_needs(tmp_path: Path) -> None:
    # Given a line behind `n > 10` true and `s == "a"` false, with a division's raising fork
    # between them
    file = module(tmp_path)

    # When the way to the line is read
    way = way_to(file, 6, [equal_to_a(file, 12)], None)

    # Then it holds both conditions in the order a run meets them, and leaves the raising one out
    assert way.conditions == (
        Condition(site=Site(file=file, line=2, col=7), side=True),
        Condition(site=Site(file=file, line=4, col=11), side=False),
    )


def test_the_furthest_input_is_the_first_that_passed_the_deepest_node(tmp_path: Path) -> None:
    # Given two inputs that stopped at `n > 10`, one that raised in the division, and two that
    # got past it to `s == "a"`
    file = module(tmp_path)
    records = [
        small(file, 0),
        small(file, -1),
        divided_by_zero(file),
        equal_to_a(file, 12),
        equal_to_a(file, 13),
    ]

    # When the way to the line behind `s == "a"` false is read
    way = way_to(file, 6, records, None)

    # Then the furthest is input 4, the first of the two that got furthest
    assert way.furthest == 4


def test_no_input_on_the_way_gives_no_furthest(tmp_path: Path) -> None:
    # Given a run whose inputs called only `handle`
    file = module(tmp_path)

    # When the way to a line of `other` is read
    way = way_to(file, 12, [small(file, 0), equal_to_a(file, 12)], None)

    # Then it lists the way's condition, and no input got along it
    assert way == Way(conditions=(Condition(site=Site(file=file, line=11, col=7), side=True),))
    assert way.furthest is None


def test_a_stop_already_passed_gives_an_empty_way(tmp_path: Path) -> None:
    # Given a stop that has already come
    file = module(tmp_path)
    stop_at = time.monotonic() - 1.0

    # When the way to a line is read
    way = way_to(file, 6, [equal_to_a(file, 12)], stop_at)

    # Then it holds no condition and no furthest input
    assert way == Way(conditions=(), furthest=None)
