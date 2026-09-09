from collections.abc import Callable

import pytest

from pyct.core.branch import Branch, Downgrade, SinkItem, Site
from pyct.core.values import ConcolicInt

# one call per untaught operation, a spread of them wide enough to stand for the whole list
DOWNGRADED_CALLS: dict[str, Callable[[int], object]] = {
    "__add__": lambda x: x + 1,
    "__radd__": lambda x: 1 + x,
    "__sub__": lambda x: x - 1,
    "__mul__": lambda x: x * 2,
    "__truediv__": lambda x: x / 2,
    "__floordiv__": lambda x: x // 2,
    "__mod__": lambda x: x % 2,
    "__divmod__": lambda x: divmod(x, 2),
    "__pow__": lambda x: x**2,
    "__lshift__": lambda x: x << 1,
    "__rshift__": lambda x: x >> 1,
    "__and__": lambda x: x & 1,
    "__or__": lambda x: x | 1,
    "__xor__": lambda x: x ^ 1,
    "__neg__": lambda x: -x,
    "__abs__": abs,
    "__invert__": lambda x: ~x,
    "__gt__": lambda x: x > 1,
    "__le__": lambda x: x <= 1,
    "__float__": float,
    "__round__": round,
}

# a probe whose text is fixed here, so the line and column of the fork are exact
PROBE = "def probe(v):\n    if v:\n        return 'yes'\n    return 'no'\n"

# a probe that tests the same value twice, so the order the sink holds is visible
TWO_CHECKS = (
    "def probe(x):\n"
    "    n = 0\n"
    "    if x < 10:\n"
    "        n += 1\n"
    "    if x < 100:\n"
    "        n += 1\n"
    "    return n\n"
)


def _probe(source: str = PROBE) -> Callable[..., object]:
    namespace: dict[str, object] = {}
    exec(compile(source, "<probe>", "exec"), namespace)
    probe = namespace["probe"]
    assert callable(probe)
    return probe


def test_a_concolic_int_is_a_real_int() -> None:
    x = ConcolicInt(3, expression="x", sink=[])

    assert isinstance(x, int)
    assert x == 3
    assert x.expression == "x"


def test_any_operation_but_less_than_returns_a_plain_int() -> None:
    x = ConcolicInt(3, expression="x", sink=[])

    assert type(x + 1) is int


def test_less_than_builds_the_expression_and_records_nothing() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    result = x < 10

    assert result.expression == ["<", "x", 10]
    assert result == True  # noqa: E712 - the value, not the truth test
    assert sink == []


def test_less_than_takes_the_other_concolics_expression() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)
    y = ConcolicInt(10, expression="y", sink=sink)

    assert (x < y).expression == ["<", "x", "y"]


def test_less_than_a_non_int_is_pythons_own_compare() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # a float is not an int, so the compare is float's and nothing symbolic is recorded
    assert (x < 3.5) is True
    assert sink == []


def test_less_than_a_bool_is_pythons_own_compare() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    assert (x < True) is False
    assert sink == []


def test_less_than_a_compares_value_is_pythons_own_compare() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(0, expression="x", sink=sink)
    y = ConcolicInt(3, expression="y", sink=sink)

    # a compare's value stands for a truth value, not a number, so `<` against it is
    # int's own: a plain bool, not a leaf that drops y's compare for its concrete 1
    assert (x < (y < 5)) is True
    assert sink == []


def test_less_than_carries_the_concrete_result() -> None:
    x = ConcolicInt(50, expression="x", sink=[])

    assert (x < 10) == False  # noqa: E712 - the value, not the truth test


def test_a_compare_adds_up_like_a_bool() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    assert sum([x < 10, x < 100]) == 2

    # sum adds, it never tests for truth
    assert sink == []


def test_a_compare_equals_the_bool_it_stands_for() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    assert (x < 10) == True  # noqa: E712 - comparing to True is what the target may do
    assert (x < 100) == True  # noqa: E712 - same

    # `==` against an int never tests for truth
    assert sink == []


def test_a_compare_reads_back_as_a_bool() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    assert repr(x < 10) == "True"
    assert repr(x < 100) == "True"

    assert sink == []


def test_the_truth_test_records_the_fork_where_it_happens() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # the compare happens here, the truth test inside the probe; the fork is the probe's
    assert _probe()(x < 10) == "yes"

    assert sink == [
        Branch(expression=["<", "x", 10], taken=True, site=Site(file="<probe>", line=2, col=7))
    ]


def test_a_reflected_compare_records_the_same_fork() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # int has no way to compare against a subclass, so Python asks x first: `x < 10`
    assert _probe()(10 > x) == "yes"  # noqa: SIM300 - the reflected form is the point

    assert sink == [
        Branch(expression=["<", "x", 10], taken=True, site=Site(file="<probe>", line=2, col=7))
    ]


def test_the_truth_test_records_the_side_it_took() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(50, expression="x", sink=sink)

    assert _probe()(x < 10) == "no"

    assert [branch.taken for branch in sink] == [False]


def test_two_truth_tests_reach_the_sink_in_the_order_they_ran() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(5, expression="x", sink=sink)

    assert _probe(TWO_CHECKS)(x) == 2

    assert sink == [
        Branch(expression=["<", "x", 10], taken=True, site=Site(file="<probe>", line=3, col=7)),
        Branch(expression=["<", "x", 100], taken=True, site=Site(file="<probe>", line=5, col=7)),
    ]


@pytest.mark.parametrize(("name", "call"), DOWNGRADED_CALLS.items(), ids=list(DOWNGRADED_CALLS))
def test_an_untaught_operation_returns_a_plain_value_and_records_its_name(
    name: str, call: Callable[[int], object]
) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    result = call(x)

    assert result == call(3)
    assert not isinstance(result, ConcolicInt)
    assert sink == [Downgrade(name=name)]


def test_a_concolic_int_hashes_like_an_int_and_records_nothing() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    assert hash(x) == hash(3)
    assert {x: "small"}[x] == "small"

    assert sink == []


def test_reading_a_concolic_int_back_records_nothing() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # repr is the debugger's path, not the target's
    assert repr(x) == "3"

    assert sink == []


def test_equality_returns_a_plain_bool_and_records_a_downgrade() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    result = x == 3

    assert result is True
    assert sink == [Downgrade(name="__eq__")]


def test_a_truth_test_on_a_concolic_int_records_a_downgrade() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    size = "yes" if x else "no"

    assert size == "yes"
    assert sink == [Downgrade(name="__bool__")]


def test_turning_a_concolic_int_into_text_records_a_downgrade() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    assert str(x) == "3"
    assert f"{x}" == "3"

    assert sink == [Downgrade(name="__str__"), Downgrade(name="__format__")]


def test_using_a_concolic_int_as_an_index_records_a_downgrade() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    assert list(range(x)) == [0, 1, 2]

    assert sink == [Downgrade(name="__index__")]


def test_an_operation_that_raises_records_nothing() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    with pytest.raises(ZeroDivisionError):
        _ = x // 0

    # nothing was lost: the raise is the target's own
    assert sink == []


def test_an_operation_the_other_type_answers_records_nothing() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # int cannot add a float, so float's reflected add answers and int's own never did
    assert x + 1.5 == 4.5

    assert sink == []


def test_a_reflected_untaught_compare_records_the_reflected_name() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # `10 < x` asks x first, as `x.__gt__(10)`; unlike `<`, `>` is not taught
    assert (10 < x) is False  # noqa: SIM300 - the reflected form is the point

    assert sink == [Downgrade(name="__gt__")]


def test_downgrades_and_a_fork_reach_the_sink_in_the_order_they_ran() -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    assert abs(x) == 3
    assert str(x) == "3"
    assert _probe()(x < 10) == "yes"

    assert sink == [
        Downgrade(name="__abs__"),
        Downgrade(name="__str__"),
        Branch(expression=["<", "x", 10], taken=True, site=Site(file="<probe>", line=2, col=7)),
    ]
