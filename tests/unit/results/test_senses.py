"""Which `in` and `is` tests read their value the other way from the forks recorded there.

Each test states the sides as the forks read them, so it holds on every release, however the
release compiles the `not`.
"""

import types

import pytest

from pyct.results.senses import against_the_forks, heads_of
from pyct.results.way import Flow, Fork, Step, StepKind


def flow_of(test: str) -> Flow:
    """The flow of `f`, which runs line 3 when the test on line 2 holds, else line 4."""
    source = f"def f(x, c):\n    if {test}:\n        return 1\n    return 2\n"
    (code,) = [each for each in compile(source, "m.py", "exec").co_consts if _is_code(each)]
    return Flow(code, frozenset())


def _is_code(each: object) -> bool:
    return isinstance(each, types.CodeType)


def body_side(flow: Flow, col: int) -> bool:
    (step,) = flow.way(3)
    assert (step.line, step.col) == (2, col)
    return step.side


# the test, the column of its site, the forks' heads there, and the side the body reads as
IN_TESTS = [
    ("not x in c", 11, {"not in"}, True),
    ("x not in c", 7, {"not in"}, True),
    ("x in c", 7, {"in"}, True),
    ("not x in c", 11, {"=="}, False),
    ("x not in c", 7, {"=="}, False),
    ("not not x in c", 15, {"in"}, True),
]


@pytest.mark.parametrize(("test", "col", "heads", "side"), IN_TESTS)
def test_an_in_test_reads_as_the_forks_recorded_at_its_site(
    test: str, col: int, heads: set[str], side: bool
) -> None:
    flow = flow_of(test)

    flow.swap(against_the_forks(flow, {(2, col): frozenset(heads)}, []))

    assert body_side(flow, col) == side


@pytest.mark.parametrize("test", ["not x in c", "x is not True", "x is False"])
def test_a_test_no_fork_was_recorded_at_reads_as_its_jump_tests(test: str) -> None:
    flow = flow_of(test)
    as_compiled = flow.way(3)

    flow.swap(against_the_forks(flow, {}, [(frozenset({2, 3}), ())]))

    assert flow.way(3) == as_compiled


def took_the_body(taken: bool) -> tuple[frozenset[int], tuple[Fork, ...]]:
    """An input that ran the body, and recorded its operand's fork at 2:7 as ``taken``."""
    return frozenset({2, 3}), ((2, 7, taken, False),)


@pytest.mark.parametrize(
    ("test", "taken"), [("x is not True", False), ("x is True", True), ("x is False", False)]
)
def test_an_is_test_reads_as_its_operand_s_fork_where_an_input_shows_both(
    test: str, taken: bool
) -> None:
    flow = flow_of(test)

    flow.swap(against_the_forks(flow, {(2, 7): frozenset({">"})}, [took_the_body(taken)]))

    assert body_side(flow, 7) == taken


def test_an_is_test_the_inputs_disagree_on_or_do_not_show_reads_as_its_jump_tests() -> None:
    heads = {(2, 7): frozenset({">"})}
    unshown: tuple[frozenset[int], tuple[Fork, ...]] = (frozenset({2}), ((2, 7, False, False),))
    for seen in ([took_the_body(False), took_the_body(True)], [unshown]):
        flow = flow_of("x is not True")

        flow.swap(against_the_forks(flow, heads, seen))

        assert flow.way(3) == (Step(StepKind.CONDITION, 2, 7, True),)


def test_heads_are_each_fork_s_operator_by_site() -> None:
    forks = [((2, 7), ["not in", "s", "'a'"]), ((2, 7), ["==", "x", 1]), ((3, 4), "b")]

    assert heads_of(forks) == {(2, 7): frozenset({"not in", "=="}), (3, 4): frozenset({"b"})}
