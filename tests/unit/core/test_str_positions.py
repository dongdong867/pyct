"""The positions a ConcolicStr is read at: a tracked int as an index, a slice bound, a step of 1
or -1, a search's start and end, a tuple of prefixes, and a replace's count."""

from collections.abc import Callable

import pytest

from pyct.core.bools import ConcolicBool
from pyct.core.branch import Branch, Expression, SinkItem, Site
from pyct.core.ints import ConcolicInt
from pyct.core.strs import ConcolicStr
from pyct.core.values import raised_by_target


def _tracked(value: str = "abcb", sink: list[SinkItem] | None = None) -> ConcolicStr:
    return ConcolicStr.made(value, expression="s", sink=[] if sink is None else sink)


def _n(value: int, sink: list[SinkItem]) -> ConcolicInt:
    return ConcolicInt.made(value, expression="n", sink=sink)


# a form on s = "abcb", a tracked n = 1 and a tracked t = "x" that records no fork: the call,
# and the expression it carries
FOLLOWED: dict[str, tuple[Callable[[str, int, str], object], Expression]] = {
    "s[n:]": (lambda s, n, t: s[n:], ["[:]", "s", "n", None]),
    "s[:n]": (lambda s, n, t: s[:n], ["[:]", "s", None, "n"]),
    "s[:n + 1]": (lambda s, n, t: s[: n + 1], ["[:]", "s", None, ["+", "n", 1]]),
    "s[None:n]": (lambda s, n, t: s[None:n], ["[:]", "s", None, "n"]),
    "s[::None]": (lambda s, n, t: s[::None], ["[:]", "s", None, None]),
    "s[::-1]": (lambda s, n, t: s[::-1], ["[:]", "s", None, None, -1]),
    "s[0:3:1]": (lambda s, n, t: s[0:3:1], ["[:]", "s", 0, 3, 1]),
    "s[n:0:-1]": (lambda s, n, t: s[n:0:-1], ["[:]", "s", "n", 0, -1]),
    "s[::True]": (lambda s, n, t: s[::True], ["[:]", "s", None, None, 1]),
    "s.find('b', n)": (lambda s, n, t: s.find("b", n), ["find", "s", "'b'", "n"]),
    "s.find('b', None, n)": (lambda s, n, t: s.find("b", None, n), ["find", "s", "'b'", None, "n"]),
    "s.find('b', 2)": (lambda s, n, t: s.find("b", 2), ["find", "s", "'b'", 2]),
    "s.rfind('b', 0, n)": (lambda s, n, t: s.rfind("b", 0, n), ["rfind", "s", "'b'", 0, "n"]),
    "s.count('b', -n)": (lambda s, n, t: s.count("b", -n), ["count", "s", "'b'", ["-", "n"]]),
    "s.startswith('b', n)": (
        lambda s, n, t: s.startswith("b", n),
        ["startswith", "s", "'b'", "n"],
    ),
    "s.endswith(t, 0, 3)": (lambda s, n, t: s.endswith(t, 0, 3), ["endswith", "s", "t", 0, 3]),
    "s.startswith(('x', 'a'))": (
        lambda s, n, t: s.startswith(("x", "a")),
        ["startswith", "s", ["()", "'x'", "'a'"]],
    ),
    "s.endswith(('b',), n)": (
        lambda s, n, t: s.endswith(("b",), n),
        ["endswith", "s", ["()", "'b'"], "n"],
    ),
    "s.startswith(('c', t))": (
        lambda s, n, t: s.startswith(("c", t)),
        ["startswith", "s", ["()", "'c'", "t"]],
    ),
    "s.replace('b', 'x', 1)": (
        lambda s, n, t: s.replace("b", "x", 1),
        ["replace", "s", "'b'", "'x'", 1],
    ),
    "s.replace('', 'x', 1)": (
        lambda s, n, t: s.replace("", "x", 1),
        ["replace", "s", "''", "'x'", 1],
    ),
    "s.replace(t, 'y', 1)": (lambda s, n, t: s.replace(t, "y", 1), ["replace", "s", "t", "'y'", 1]),
    "s.replace('', 'x', 0)": (
        lambda s, n, t: s.replace("", "x", 0),
        ["replace", "s", "''", "'x'", 0],
    ),
    "s.replace('b', 'x', -1)": (
        lambda s, n, t: s.replace("b", "x", -1),
        ["replace", "s", "'b'", "'x'", -1],
    ),
    "s.replace('b', 'x', True)": (
        lambda s, n, t: s.replace("b", "x", True),
        ["replace", "s", "'b'", "'x'", 1],
    ),
}


@pytest.mark.parametrize(("call", "expression"), FOLLOWED.values(), ids=list(FOLLOWED))
def test_a_form_with_a_position_is_followed_and_records_nothing(
    call: Callable[[str, int, str], object], expression: Expression
) -> None:
    sink: list[SinkItem] = []

    result = call(
        _tracked(sink=sink), _n(1, sink), ConcolicStr.made("x", expression="t", sink=sink)
    )

    assert isinstance(result, ConcolicStr | ConcolicInt | ConcolicBool)
    assert result.expression == expression
    # the plain value underneath is Python's own answer
    plain = call("abcb", 1, "x")
    assert type(plain).__eq__(plain, result) is True
    assert sink == []


def test_an_empty_tuple_is_strs_plain_false_and_records_nothing() -> None:
    sink: list[SinkItem] = []
    s = _tracked(sink=sink)

    # the answer reads nothing of s, so there is no condition to keep
    assert s.startswith(()) is False
    assert s.endswith((), _n(1, sink)) is False
    assert sink == []


# a probe whose text is fixed here, so the line and column of each fork are exact
PROBE = "def probe(v, i):\n    return v[i]\n"
SITE = Site("<probe>", 2, 11)


def _probe() -> Callable[[object, object], object]:
    namespace: dict[str, object] = {}
    exec(compile(PROBE, "<probe>", "exec"), namespace)
    probe = namespace["probe"]
    assert callable(probe)
    return probe


LONG_ENOUGH: Expression = [">", ["len", "s"], "n"]
NOT_TOO_SHORT: Expression = [">=", ["len", "s"], ["-", "n"]]


@pytest.mark.parametrize("index", [0, 3, -1, -4])
def test_a_tracked_index_in_range_records_both_forks_taken(index: int) -> None:
    sink: list[SinkItem] = []

    result = _probe()(_tracked(sink=sink), _n(index, sink))

    assert sink == [
        Branch(expression=LONG_ENOUGH, taken=True, site=SITE),
        Branch(expression=NOT_TOO_SHORT, taken=True, site=SITE),
    ]
    assert isinstance(result, ConcolicStr)
    assert result.expression == ["[]", "s", "n"]
    assert str.__eq__(result, "abcb"[index]) is True


@pytest.mark.parametrize(
    ("index", "sides"),
    [(4, [False]), (9, [False]), (-5, [True, False])],
    ids=["past the end", "far past the end", "before the start"],
)
def test_a_tracked_index_out_of_range_records_its_forks_and_raises_as_the_targets(
    index: int, sides: list[bool]
) -> None:
    sink: list[SinkItem] = []

    with pytest.raises(IndexError) as raised:
        _probe()(_tracked(sink=sink), _n(index, sink))

    assert raised_by_target(raised.value)
    forks = [LONG_ENOUGH, NOT_TOO_SHORT][: len(sides)]
    assert sink == [
        Branch(expression=fork, taken=side, site=SITE)
        for fork, side in zip(forks, sides, strict=True)
    ]


def test_an_index_of_a_tracked_arithmetic_measures_its_expression() -> None:
    sink: list[SinkItem] = []
    n = _n(1, sink) + 1
    sink.clear()

    result = _tracked(sink=sink)[n]

    assert _expression_of(result) == ["[]", "s", ["+", "n", 1]]
    assert [item.expression for item in sink if isinstance(item, Branch)] == [
        [">", ["len", "s"], ["+", "n", 1]],
        [">=", ["len", "s"], ["-", ["+", "n", 1]]],
    ]


def _expression_of(result: object) -> Expression:
    assert isinstance(result, ConcolicStr), result
    return result.expression


RAISING_PROBE = "def probe(v, *args):\n    return v.{name}(*args)\n"


def _raising_probe(name: str) -> Callable[..., object]:
    namespace: dict[str, object] = {}
    exec(compile(RAISING_PROBE.format(name=name), "<probe>", "exec"), namespace)
    probe = namespace["probe"]
    assert callable(probe)
    return probe


# a raising search from a position on s = "abcb" with a tracked n = 1: the search, the needle,
# the fork it records first, and its answer
FOUND_FROM_A_POSITION: dict[str, tuple[str, str, Expression, int]] = {
    "s.index('b', n)": ("index", "b", ["!=", ["find", "s", "'b'", "n"], -1], 1),
    "s.rindex('b', n)": ("rindex", "b", ["!=", ["rfind", "s", "'b'", "n"], -1], 3),
    "s.index('', n)": ("index", "", ["!=", ["find", "s", "''", "n"], -1], 1),
}


@pytest.mark.parametrize(
    ("name", "sub", "fork", "answer"),
    FOUND_FROM_A_POSITION.values(),
    ids=list(FOUND_FROM_A_POSITION),
)
def test_a_raising_search_from_a_position_records_the_search_it_mirrors(
    name: str, sub: str, fork: Expression, answer: int
) -> None:
    sink: list[SinkItem] = []

    result = _raising_probe(name)(_tracked(sink=sink), sub, _n(1, sink))

    assert isinstance(result, ConcolicInt)
    assert result.expression == [name, "s", repr(sub), "n"]
    assert int.__index__(result) == answer
    assert sink == [Branch(expression=fork, taken=True, site=SITE)]


@pytest.mark.parametrize(
    ("name", "args", "fork"),
    [
        ("rindex", ("b", 0), ["!=", ["rfind", "s", "'b'", 0, "n"], -1]),
        # an empty sub past the end is not found, where `"" in s[5:]` would say it is
        ("index", ("",), ["!=", ["find", "s", "''", "n"], -1]),
    ],
    ids=["s.rindex('b', 0, n)", "s.index('', n)"],
)
def test_a_raising_search_from_a_position_that_finds_nothing_raises_after_its_fork(
    name: str, args: tuple[object, ...], fork: Expression
) -> None:
    sink: list[SinkItem] = []
    n = _n(1 if name == "rindex" else 5, sink)

    with pytest.raises(ValueError) as plain:
        getattr("abcb", name)(*args, int.__index__(n))
    with pytest.raises(ValueError) as raised:
        _raising_probe(name)(_tracked(sink=sink), *args, n)

    # Python's own sentence, as plain Python words it in this run
    assert str(raised.value) == str(plain.value)
    assert raised_by_target(raised.value)
    assert sink == [Branch(expression=fork, taken=False, site=SITE)]
