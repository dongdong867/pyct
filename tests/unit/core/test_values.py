from collections.abc import Callable

from pyct.core.branch import Branch, Site
from pyct.core.values import ConcolicInt

# a probe whose text is fixed here, so the line and column of the fork are exact
PROBE = "def probe(v):\n    if v:\n        return 'yes'\n    return 'no'\n"


def _probe() -> Callable[..., object]:
    namespace: dict[str, object] = {}
    exec(compile(PROBE, "<probe>", "exec"), namespace)
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
    sink: list[Branch] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    result = x < 10

    assert result.value is True
    assert result.expression == ["<", "x", 10]
    assert sink == []


def test_less_than_takes_the_other_concolics_expression() -> None:
    sink: list[Branch] = []
    x = ConcolicInt(3, expression="x", sink=sink)
    y = ConcolicInt(10, expression="y", sink=sink)

    assert (x < y).expression == ["<", "x", "y"]


def test_less_than_carries_the_concrete_result() -> None:
    x = ConcolicInt(50, expression="x", sink=[])

    assert (x < 10).value is False


def test_the_truth_test_records_the_fork_where_it_happens() -> None:
    sink: list[Branch] = []
    x = ConcolicInt(3, expression="x", sink=sink)

    # the compare happens here, the truth test inside the probe; the fork is the probe's
    assert _probe()(x < 10) == "yes"

    assert sink == [
        Branch(expression=["<", "x", 10], taken=True, site=Site(file="<probe>", line=2, col=7))
    ]


def test_the_truth_test_records_the_side_it_took() -> None:
    sink: list[Branch] = []
    x = ConcolicInt(50, expression="x", sink=sink)

    assert _probe()(x < 10) == "no"

    assert [branch.taken for branch in sink] == [False]
