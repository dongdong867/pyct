"""The table of tracked number types: a result's own Python type picks its tracked class."""

import subprocess
import sys
import textwrap

import pytest

from pyct.core import numbers
from pyct.core.bools import ConcolicBool
from pyct.core.branch import BranchSink, Expression, SinkItem
from pyct.core.ints import ConcolicInt


class Tracked(int):
    """A stand-in tracked class, entered for a stand-in base type."""

    expression: Expression

    def __new__(cls, value: int, *, expression: Expression, sink: BranchSink) -> "Tracked":
        self = super().__new__(cls, value)
        self.expression = expression
        return self


class Base(int):
    """A stand-in Python type a result could have."""


class Reading(float):
    """A stand-in Python type outside the int family, which nothing in pyct enters."""


class Measured(float):
    """A stand-in tracked number outside the int family, as a tracked float will be."""

    expression: Expression

    def __new__(cls, value: float, *, expression: Expression, sink: BranchSink) -> "Measured":
        self = super().__new__(cls, value)
        self.expression = expression
        return self


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> None:
    """A copy of the table for one test, so an entry made here is gone after it."""
    monkeypatch.setattr(numbers, "_TRACKED", dict(numbers._TRACKED))
    monkeypatch.setattr(numbers, "_CLASSES", set(numbers._CLASSES))


def test_a_result_is_tracked_by_the_class_its_own_type_entered() -> None:
    sink: list[SinkItem] = []

    number = numbers.tracked(3, ["+", "x", 1], sink)
    truth = numbers.tracked(True, [">", "x", 0], sink)

    assert type(number) is ConcolicInt
    assert type(truth) is ConcolicBool
    assert (number.expression, truth.expression) == (["+", "x", 1], [">", "x", 0])
    assert number.sink is sink


def test_a_type_nothing_entered_fails_where_it_is_tracked() -> None:
    # a quietly plain value would lose the condition without a word; this names the gap
    with pytest.raises(LookupError, match="no tracked type is entered for Reading"):
        numbers.tracked(Reading(2.5), ["/", "x", 2], [])


@pytest.mark.usefixtures("table")
def test_a_type_enters_its_class_once() -> None:
    numbers.enter(Base, Tracked)
    numbers.enter(Base, Tracked)

    assert type(numbers.tracked(Base(4), "x", [])) is Tracked
    assert numbers.operand(Tracked(4, expression="x", sink=[])) == "x"


@pytest.mark.usefixtures("table")
def test_a_second_class_for_a_type_is_refused() -> None:
    # two classes for one type would make the answer depend on which module Python read last
    with pytest.raises(ValueError, match="int is already tracked by ConcolicInt"):
        numbers.enter(int, Tracked)


@pytest.mark.usefixtures("table")
def test_an_int_leaves_a_tracked_number_outside_its_family_to_that_number() -> None:
    # entered for a stand-in type, so a tracked float entered for float leaves this test alone
    numbers.enter(Reading, Measured)
    sink: list[SinkItem] = []
    x = ConcolicInt(5, expression="x", sink=sink)
    f = Measured(2.5, expression="f", sink=sink)

    # int's own answers NotImplemented to a float, so Python asks the float, as it does unwatched
    assert numbers.operand(f) is None
    assert (x < f) is False
    assert (x == f) is False
    assert type(x + f) is float and x + f == 7.5
    assert type(x // f) is float and x // f == 2.0
    # no fork and no downgrade: nothing int's side taught ran
    assert sink == []


def test_an_operand_reads_as_a_number_does() -> None:
    x = ConcolicInt(3, expression="x", sink=[])

    # a tracked number by its expression, a plain int or bool as itself, anything else not at all
    assert numbers.operand(x) == "x"
    assert numbers.operand(x > 0) == [">", "x", 0]
    assert numbers.operand(5) == 5
    assert numbers.operand(True) is True
    assert numbers.operand(2.5) is None
    assert numbers.operand("5") is None


# the table is read from the numbers module alone, in an interpreter that imported nothing else
TABLE_ALONE = textwrap.dedent(
    """
    from pyct.core.numbers import tracked

    print(type(tracked(1, "x", [])).__name__, type(tracked(True, "x", [])).__name__)
    """
)


def test_the_table_is_full_whichever_core_module_is_imported_first() -> None:
    # this session has already imported every core module, so only a fresh interpreter shows
    # that pyct.core fills the table before a caller reaches numbers
    result = subprocess.run(
        [sys.executable, "-c", TABLE_ALONE], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "ConcolicInt ConcolicBool\n"
