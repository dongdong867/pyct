"""The note on each fork an `is` records of its operand: whether the `is` held on that pass."""

import pytest

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, SinkItem, Site
from pyct.core.substitutes import is_, is_not


def tracked_bool(value: bool, sink: list[SinkItem]) -> ConcolicBool:
    return ConcolicBool.made(value, expression=[">", "x", 5], sink=sink)


def notes(sink: list[SinkItem]) -> list[tuple[bool, bool | None]]:
    """Each fork's side and its note."""
    return [(item.taken, item.is_held) for item in sink if isinstance(item, Branch)]


@pytest.mark.parametrize(
    ("value", "call", "held"),
    [
        (True, lambda b: is_(b, True), True),
        (False, lambda b: is_(b, True), False),
        (True, lambda b: is_(b, False), False),
        (False, lambda b: is_(False, b), True),
        (True, lambda b: is_not(b, False), False),
        (False, lambda b: is_not(True, b), False),
    ],
)
def test_a_tracked_bool_s_fork_notes_whether_its_is_held(
    value: bool, call: object, held: bool
) -> None:
    sink: list[SinkItem] = []

    call(tracked_bool(value, sink))  # pyrefly: ignore[not-callable]

    assert notes(sink) == [(value, held)]


@pytest.mark.parametrize(("left", "right"), [(True, True), (True, False)])
def test_two_tracked_bools_note_their_equality_as_the_is(left: bool, right: bool) -> None:
    sink: list[SinkItem] = []
    flag = ConcolicBool.made(left, expression="flag", sink=sink)
    other = ConcolicBool.made(right, expression="other", sink=sink)

    is_(flag, other)

    assert notes(sink) == [(left is right, left is right)]


def test_a_truth_test_outside_an_is_has_no_note() -> None:
    sink: list[SinkItem] = []
    b = tracked_bool(True, sink)

    is_(b, False)
    bool(b)

    assert notes(sink) == [(True, False), (True, None)]


def test_the_note_is_no_part_of_the_fork() -> None:
    site = Site(file="t.py", line=3, col=7)

    assert Branch("b", True, site, is_held=False) == Branch("b", True, site)
    assert hash(Branch("b", True, site, is_held=True)) == hash(Branch("b", True, site))
