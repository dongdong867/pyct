"""The sense of the fork pyct records at each membership and identity test."""

import pytest

from pyct.results.graphs import Pace, UnaffordableError
from pyct.results.senses import negated_sites
from pyct.results.way import Flow, Step, StepKind

# a compare on line 2 at column 7, and whether the fork pyct records there is negated
RECORDED = [
    ("x in c", False),
    ("x not in c", True),
    ("not x in c", True),
    ("not (x not in c)", False),
    ("not not x in c", False),
    ("x is True", False),
    ("x is not True", False),
    ("True is x", False),
    ("x is False", True),
    ("not x is False", True),
]


@pytest.mark.parametrize(("test", "negated"), RECORDED)
def test_a_site_says_whether_its_recorded_fork_is_negated(test: str, negated: bool) -> None:
    compare = test.removeprefix("not (").removeprefix("not not ").removeprefix("not ")
    column = 7 + test.index(compare)
    source = f"def f(x, c):\n    if {test}:\n        return 1\n"

    assert negated_sites(source, Pace()) == {(2, column): negated}


@pytest.mark.parametrize(
    "test", ["x is None", "x is y", "x is True is y", "x < y", "x is True is not False"]
)
def test_a_compare_with_no_fork_of_its_own_in_a_known_sense_has_no_site(test: str) -> None:
    assert negated_sites(f"def f(x, y):\n    if {test}:\n        pass\n", Pace()) == {}


def test_a_source_too_large_to_parse_before_the_stop_is_not_read() -> None:
    late = Pace(late=lambda ahead: ahead > 0.0)

    with pytest.raises(UnaffordableError):
        negated_sites("x in c\n" * 1000, late)


# `not x in c` tested on line 2; line 3 is its body, and line 4 comes after it
NOT_IN = "def f(x, c):\n    if not x in c:\n        return 1\n    return 2\n"


def test_a_flow_reads_a_test_s_sides_in_the_sense_of_its_recorded_fork() -> None:
    (code,) = [
        each for each in compile(NOT_IN, "m.py", "exec").co_consts if hasattr(each, "co_code")
    ]
    asked: list[bool] = []

    def negated(pace: Pace) -> dict[tuple[int, int], bool]:
        asked.append(True)
        return negated_sites(NOT_IN, pace)

    flow = Flow(code, frozenset(), negated=negated)

    # the body is the true side of `x not in c` on every release, as pyct records it
    assert flow.way(3) == (Step(StepKind.CONDITION, 2, 11, True),)
    assert flow.way(4) == (Step(StepKind.CONDITION, 2, 11, False),)
    assert asked == [True]


def test_a_flow_with_no_test_of_in_or_is_never_asks_for_the_sites() -> None:
    code = compile("def f(x):\n    if x:\n        return 1\n", "m.py", "exec").co_consts[0]

    def negated(pace: Pace) -> dict[tuple[int, int], bool]:
        raise AssertionError("asked")

    assert Flow(code, frozenset(), negated=negated).way(3) == (
        Step(StepKind.CONDITION, 2, 7, True),
    )
