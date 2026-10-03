"""The length range a tracked value keeps, and what it proves, held against Python."""

import itertools

import pytest

from pyct.core.branch import Branch, Fact, SinkItem
from pyct.core.spans import (
    UNKNOWN,
    Span,
    added,
    cut_out,
    decided,
    exactly,
    narrowed,
    proves,
    repeated,
    scaled,
    sliced,
)

# every bound a slice in these tests is cut with, missing ones included
BOUNDS = [None, -4, -2, -1, 0, 1, 2, 3, 5]
# ranges with a most, and each length inside them
CLOSED = [(0, 0), (0, 3), (1, 4), (2, 2), (3, 7), (5, 9)]
OPS = ["<", "<=", ">", ">=", "==", "!="]


def lengths(span: Span) -> range:
    fewest, most = span
    assert fewest is not None and most is not None
    return range(fewest, most + 1)


@pytest.mark.parametrize("span", CLOSED)
def test_a_slice_s_range_is_python_s_clamp_at_every_length(span: Span) -> None:
    for start, stop, step in itertools.product(BOUNDS, BOUNDS, [None, 1, -1]):
        cut = slice(start, stop, step)
        counts = [len(range(count)[cut]) for count in lengths(span)]
        assert sliced(span, start, stop, step) == (min(counts), max(counts)), cut


@pytest.mark.parametrize("span", CLOSED)
def test_a_deleted_slice_leaves_what_python_leaves_at_every_length(span: Span) -> None:
    for start, stop in itertools.product(BOUNDS, BOUNDS):
        cut = slice(start, stop)
        counts = [count - len(range(count)[cut]) for count in lengths(span)]
        assert cut_out(span, start, stop) == (min(counts), max(counts)), cut


def test_a_slice_of_an_unbounded_range_grows_or_stays() -> None:
    assert sliced((2, None), 1, None) == (1, None)
    assert sliced((0, None), None, 3) == (0, 3)
    assert sliced((0, None), -2, None) == (0, 2)
    # past its bounds a slice from the end and up to a fixed stop holds nothing
    assert sliced((0, None), -3, 2) == (0, 2)
    assert cut_out((4, None), 1, None) == (1, 1)
    assert cut_out((0, None), None, 2) == (0, None)


def test_joins_repeats_and_plain_arithmetic_move_both_ends() -> None:
    assert added((1, 3), (2, None)) == (3, None)
    assert added((1, 3), exactly(-1)) == (0, 2)
    assert repeated((1, 3), 2) == (2, 6)
    assert repeated((1, None), 0) == (0, 0) and repeated((1, None), -2) == (0, 0)
    # a negative factor swaps the ends, and an end with no bound stays unbounded
    assert scaled((1, None), -1) == (None, -1)
    assert scaled((2, 3), 0) == (0, 0)


@pytest.mark.parametrize("span", CLOSED)
def test_a_range_proves_a_compare_only_when_every_length_in_it_agrees(span: Span) -> None:
    for op, number in itertools.product(OPS, range(-1, 11)):
        answers = {_compare(op, count, number) for count in lengths(span)}
        expected = answers.pop() if len(answers) == 1 else None
        assert proves(span, op, number) is expected, (op, number)


@pytest.mark.parametrize("span", CLOSED)
def test_a_fork_narrows_the_range_to_the_lengths_that_answer_as_it_took(span: Span) -> None:
    for op, number, taken in itertools.product(OPS, range(-1, 11), [True, False]):
        kept = [count for count in lengths(span) if _compare(op, count, number) is taken]
        if not kept:
            continue
        fewest, most = narrowed(span, op, number, taken)
        assert fewest is not None and fewest <= min(kept), (op, number, taken)
        assert most is None or most >= max(kept), (op, number, taken)
        # the ends move as far as an interval can: each end is a length that answers so
        assert _compare(op, fewest, number) is taken and (most is None or most in kept)


def test_an_unbounded_range_says_nothing_of_a_most() -> None:
    assert proves(UNKNOWN, ">", 0) is None
    assert proves((1, None), ">", 0) is True
    assert proves((1, None), "<", 1) is False
    assert proves((1, None), "==", 0) is False and proves((1, None), "!=", 0) is True
    assert narrowed(UNKNOWN, ">", 2, False) == (0, 2)
    assert narrowed(UNKNOWN, "==", 2, True) == (2, 2)


def test_a_fork_the_range_could_not_hold_leaves_what_the_fork_says() -> None:
    assert narrowed((3, 3), ">", 5, True) == (6, None)


def test_a_check_the_range_proves_is_recorded_as_a_fact() -> None:
    sink: list[SinkItem] = []

    assert decided(sink, (2, 2), [">", ["len", "xs"], 1], True)
    assert not decided(sink, (2, 2), [">", ["len", "xs"], 2], True)
    assert not decided(sink, (0, 2), [">", ["len", "xs"], 1], True)

    assert [type(item) for item in sink] == [Fact]
    assert not [item for item in sink if isinstance(item, Branch)]


def _compare(op: str, left: int, right: int) -> bool:
    return {
        "<": left < right,
        "<=": left <= right,
        ">": left > right,
        ">=": left >= right,
        "==": left == right,
        "!=": left != right,
    }[op]
