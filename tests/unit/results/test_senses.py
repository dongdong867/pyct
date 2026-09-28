"""How each `in` and `is` test's sides read, the same on every release.

Each test states the sides in the sense they read, so it holds on every release, however the
release compiles the `not`.
"""

import types

import pytest

from pyct.results import senses
from pyct.results.senses import Seen, against_the_forks, heads_of
from pyct.results.way import Flow, Step, StepKind


def flow_of(test: str, raising: frozenset[tuple[int, int]] = frozenset()) -> Flow:
    """The flow of `f`, which runs line 3 when the test on line 2 holds, else line 4."""
    source = f"def f(x, c, b):\n    if {test}:\n        return 1\n    return 2\n"
    (code,) = [each for each in compile(source, "m.py", "exec").co_consts if _is_code(each)]
    return Flow(code, raising)


def _is_code(each: object) -> bool:
    return isinstance(each, types.CodeType)


def body_side(test: str, heads: set[str], seen: list[Seen], col: int = 7) -> bool:
    """The side of the test the body reads as, with these forks recorded at 2:``col``."""
    flow = flow_of(test)
    recorded = {(2, col): frozenset(heads)} if heads else {}
    flow.swap(against_the_forks(flow, recorded, seen))
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
    # no fork, and a fork of each kind: read in the `in` sense
    ("not x in c", 11, set(), False),
    ("x not in c", 7, set(), False),
    ("x not in c", 7, {"not in", "=="}, False),
]


@pytest.mark.parametrize(("test", "col", "heads", "side"), IN_TESTS)
def test_an_in_test_reads_in_the_in_sense_or_as_its_not_in_forks(
    test: str, col: int, heads: set[str], side: bool
) -> None:
    assert body_side(test, heads, [], col) == side


# with no fork, in the `is` sense; with its operand's fork, in the operand's sense
IS_TESTS = [
    ("x is not True", set(), False),
    ("x is False", set(), True),
    ("x is not True", {">"}, False),
    ("x is True", {">"}, True),
    ("x is False", {">"}, False),
    ("True is not x", {">"}, False),
    ("x is not False", {">"}, True),
    # a True or False on the left, against an operand of many instructions
    ("False is (x < 9)", {">"}, False),
    ("False is c(x)", {">"}, False),
    ("True is not x.real", {">"}, False),
    # a lone True or False against an operand a jump runs through, on either side
    ("(c if b else x) is False", {">"}, False),
    ("False is (c if b else x)", {">"}, False),
    # an operand whose value a jump decides is no constant, so no input shows the sense: `is`
    ("(b or False) is x", {">"}, True),
    ("x is (b or True)", {">"}, True),
]


@pytest.mark.parametrize(("test", "heads", "side"), IS_TESTS)
def test_an_is_test_against_a_bool_reads_as_the_code_says(
    test: str, heads: set[str], side: bool
) -> None:
    assert body_side(test, heads, []) == side


def test_a_statement_before_the_test_lends_it_no_constant() -> None:
    # 3.13 and 3.14 load both locals of `x is b` in one instruction, after `n = False`
    source = "def f(x, b):\n    n = False\n    if x is b:\n        return n\n    return 2\n"
    (code,) = [each for each in compile(source, "m.py", "exec").co_consts if _is_code(each)]
    flow = Flow(code, frozenset())

    reads = [step.reads for step in flow.sides().values() if step.reads is not None]

    assert reads and all(each.flag is None for each in reads)


def test_the_inputs_are_not_read_when_no_is_test_is_against_a_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read: list[object] = []
    monkeypatch.setattr(senses, "_taken_at", lambda *args: read.append(args) or {})
    flow = flow_of("x is not True")

    against_the_forks(flow, {(2, 7): frozenset({">"})}, [took_the_body(False)])

    assert read == []


def took_the_body(taken: bool) -> Seen:
    """An input that ran the body, and recorded its operand's fork at 2:7 as ``taken``."""
    return frozenset({2, 3}), ((2, 7, taken, False),)


def test_an_is_test_against_a_name_reads_as_the_inputs_show() -> None:
    unshown: Seen = (frozenset({2}), ((2, 7, False, False),))

    assert body_side("x is b", {">"}, [took_the_body(False)]) is False
    assert body_side("x is b", {">"}, [took_the_body(True)]) is True
    # inputs that disagree, or show no side, leave the `is` sense
    assert body_side("x is b", {">"}, [took_the_body(False), took_the_body(True)]) is True
    assert body_side("x is not b", {">"}, [unshown]) is False


def test_a_constant_decides_an_is_test_whatever_the_inputs_show() -> None:
    # a loop's plain pass may run the body while its tracked pass forked the other way
    assert body_side("x is True", {">"}, [took_the_body(False)]) is True


def test_each_link_of_a_chain_at_one_site_is_read_on_its_own() -> None:
    flow = flow_of("x not in c is b")

    # the `not in` link reads in the `in` sense its `==` forks give; the `is` link keeps its own
    swapped = against_the_forks(flow, {(2, 7): frozenset({"=="})}, [])

    sides = flow.sides()
    read = [sides[node].reads for node in swapped]
    assert read and all(each is not None and each.name == "CONTAINS_OP" for each in read)


def test_a_raising_fork_at_the_compare_s_column_leaves_the_compare_read() -> None:
    # `x[0]` may raise, so its fork at 2:11 splits the block before the test's jump
    flow = flow_of("not x[0] in c", raising=frozenset({(2, 11)}))

    flow.swap(against_the_forks(flow, {(2, 11): frozenset({"not in"})}, []))

    assert [step for step in flow.way(3) if not step.raising] == [
        Step(StepKind.CONDITION, 2, 11, True)
    ]


def test_heads_are_each_fork_s_operator_by_site() -> None:
    forks = [((2, 7), ["not in", "s", "'a'"]), ((2, 7), ["==", "x", 1]), ((3, 4), "b")]

    assert heads_of(forks) == {(2, 7): frozenset({"not in", "=="}), (3, 4): frozenset({"b"})}
