"""A split's list's length range in core: where it starts, held against Python on every string,
and how a compare of its count with a plain int narrows it, so a check it proves is a fact."""

import itertools
from typing import Any

import pytest

from pyct.core import bound
from pyct.core.branch import Branch, Fact, SinkItem
from pyct.core.ints import ConcolicInt
from pyct.core.spans import UNKNOWN
from pyct.core.strs import ConcolicStr
from tests.unit.core.test_list_reads import tracked

# strings with no piece, one piece and many, by each separator and by whitespace and line ends
TEXTS = ["", ",", "a", "a,b", ",,", "a,,b,", " ", "a b", "  a  b c ", "\n", "a\nb", "a\r\nb\n"]
# the limits a split is called with: none, below zero, zero, plain ints and bools
LIMITS: list[Any] = [-5, -1, 0, 1, 2, 3, True, False]


def _tracked(text: str, sink: list[SinkItem] | None = None) -> Any:
    return ConcolicStr.made(text, expression="s", sink=[] if sink is None else sink)


def _count(value: Any) -> Any:
    """`len` as pyct binds it in the target's package: a split's count is a tracked int."""
    return bound.len(value)


def _within(span: Any, count: int) -> bool:
    fewest, most = span
    return fewest <= count and (most is None or count <= most)


# (the call, its range): the split by a separator, by whitespace, and splitlines
CALLS: list[tuple[str, Any, Any]] = [
    ("split", lambda s: s.split(","), (1, None)),
    ("rsplit", lambda s: s.rsplit(","), (1, None)),
    ("split by a keyword", lambda s: s.split(sep=","), (1, None)),
    ("split by whitespace", lambda s: s.split(), UNKNOWN),
    ("split by None", lambda s: s.split(None), UNKNOWN),
    ("rsplit by whitespace", lambda s: s.rsplit(), UNKNOWN),
    ("splitlines", lambda s: s.splitlines(), UNKNOWN),
    ("splitlines keeping ends", lambda s: s.splitlines(True), UNKNOWN),
]


@pytest.mark.parametrize(
    ("call", "span"), [(c, s) for _, c, s in CALLS], ids=[n for n, *_ in CALLS]
)
def test_a_split_starts_with_the_range_its_call_gives(call: Any, span: Any) -> None:
    for text in TEXTS:
        parts = call(_tracked(text))
        assert parts.span == span, text
        assert _within(span, len(call(text))), text


@pytest.mark.parametrize(
    ("name", "separator"), list(itertools.product(["split", "rsplit"], [",", None]))
)
def test_a_plain_limit_caps_a_split_at_one_more_piece(name: str, separator: Any) -> None:
    for text, limit in itertools.product(TEXTS, LIMITS):
        for parts, plain in [
            (
                getattr(_tracked(text), name)(separator, limit),
                getattr(text, name)(separator, limit),
            ),
            (getattr(_tracked(text), name)(separator, maxsplit=limit), None),
        ]:
            fewest = 0 if separator is None else 1
            most = None if limit < 0 else int(limit) + 1
            assert parts.span == (fewest, most), (text, limit)
            if plain is not None:
                assert _within(parts.span, len(plain)), (text, limit)


def _facts(sink: list[SinkItem]) -> list[object]:
    return [item.expression for item in sink if isinstance(item, Fact)]


def _forks(sink: list[SinkItem]) -> list[object]:
    return [item.expression for item in sink if isinstance(item, Branch)]


def test_a_separator_split_s_truth_test_and_first_index_are_facts() -> None:
    sink: list[SinkItem] = []
    parts = _tracked("a,b", sink).split(",")

    assert bool(parts)
    assert parts[0] == "a"
    count = ["len", ["split", "s", "','"]]
    assert ["!=", count, 0] in _facts(sink)
    assert [">", count, 0] in _facts(sink)
    assert [e for e in _forks(sink) if isinstance(e, list) and count in e] == []


def test_an_index_past_a_limited_split_is_a_fact_before_the_raise() -> None:
    sink: list[SinkItem] = []
    parts = _tracked("a,b,c", sink).split(",", 1)

    with pytest.raises(IndexError):
        parts[2]
    assert _facts(sink) == [[">", ["len", ["split", "s", "','", 1]], 2]]
    assert _forks(sink) == []


# a count compared with a plain int, how, and the range it leaves a split of four pieces
NARROWING: list[tuple[str, Any, Any]] = [
    ("equal", lambda n: n == 4, (4, 4)),
    ("not equal", lambda n: n != 3, (1, None)),
    ("more", lambda n: n > 2, (3, None)),
    ("at most", lambda n: n <= 6, (1, 6)),
    ("less one", lambda n: n - 1 > 2, (4, None)),
    ("plus", lambda n: n + 2 == 6, (4, 4)),
    ("doubled", lambda n: n * 2 == 8, (4, 4)),
    ("doubled, odd", lambda n: n * 2 < 9, (1, 4)),
    ("from the right", lambda n: 3 < n, (4, None)),  # noqa: SIM300
    ("subtracted from", lambda n: 9 - n >= 5, (1, 4)),
    ("times minus one", lambda n: n * -1 > -5, (1, 4)),
    ("twice", lambda n: 2 * (n + 1) == 10, (4, 4)),
]


@pytest.mark.parametrize(
    ("check", "span"), [(c, s) for _, c, s in NARROWING], ids=[n for n, *_ in NARROWING]
)
def test_a_count_compared_with_a_plain_int_narrows_the_split_s_range(check: Any, span: Any) -> None:
    sink: list[SinkItem] = []
    parts = _tracked("a,b,c,d", sink).split(",")

    assert bool(check(_count(parts)))
    assert parts.span == span
    assert len(_forks(sink)) == 1


def test_a_count_the_path_compared_decides_a_later_check() -> None:
    sink: list[SinkItem] = []
    parts = _tracked("a,b,c,d", sink).split(",")

    assert _count(parts) == 4
    count = _count(parts)
    assert bool(count > 2)
    assert parts[3] == "d"
    measured = ["len", ["split", "s", "','"]]
    assert _forks(sink)[:1] == [["==", measured, 4]]
    assert [">", measured, 2] in _facts(sink)
    assert [">", measured, 3] in _facts(sink)


def test_a_count_kept_from_before_reads_the_range_the_path_narrowed() -> None:
    sink: list[SinkItem] = []
    parts = _tracked("a,b,c,d", sink).split(",")
    count = _count(parts)

    assert count == 4
    assert count > 2
    assert len(_forks(sink)) == 1
    assert len(_facts(sink)) == 1


def test_a_split_s_count_left_untested_narrows_nothing() -> None:
    parts = _tracked("a,b,c,d").split(",")

    equal = _count(parts) == 4
    assert parts.span == (1, None)
    assert isinstance(equal, int)


@pytest.mark.parametrize(
    "check",
    [
        lambda n, k: n == k,
        lambda n, k: n + k > 3,
        lambda n, k: n == 4.0,
        lambda n, k: n + True == 5,
        lambda n, k: n // 2 == 2,
        lambda n, k: n % 3 == 1,
    ],
    ids=["a tracked int", "plus a tracked int", "a float", "plus a bool", "halved", "a remainder"],
)
def test_a_count_compared_with_anything_else_narrows_nothing(check: Any) -> None:
    sink: list[SinkItem] = []
    parts = _tracked("a,b,c,d", sink).split(",")
    tracked_int = ConcolicInt.made(4, expression="k", sink=sink)

    bool(check(_count(parts), tracked_int))
    assert parts.span == (1, None)


def test_a_count_taken_before_a_change_narrows_nothing() -> None:
    sink: list[SinkItem] = []
    parts = _tracked("a,b,c,d", sink).split(",")
    count = _count(parts)

    parts.append("e")
    assert count == 4
    assert parts.span == (2, None)


def test_a_count_of_a_list_made_from_a_split_narrows_that_list() -> None:
    sink: list[SinkItem] = []
    parts = _tracked("a,b", sink).split(",") + ["z"]

    assert parts.span == (2, None)
    assert _count(parts) == 3
    assert parts.span == (3, 3)


def test_a_count_of_another_list_narrows_nothing() -> None:
    items, sink = tracked([1, 2, 3, 4])

    assert _count(items) == 4
    assert items.span == UNKNOWN
    assert _count(items) > 2
    assert _facts(sink) == []
