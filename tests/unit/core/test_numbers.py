"""The table of tracked number types: a result's own Python type picks its tracked class."""

import subprocess
import sys
import textwrap

import pytest

from pyct.core import numbers
from pyct.core.bools import ConcolicBool
from pyct.core.branch import BranchSink, Expression, SinkItem
from pyct.core.floats import ConcolicFloat
from pyct.core.ints import ConcolicInt


class Tracked(int):
    """A stand-in tracked class, entered for a stand-in base type."""

    expression: Expression

    @classmethod
    def made(cls, value: int, expression: Expression, sink: BranchSink) -> "Tracked":
        made = cls(value)
        made.expression = expression
        return made


class Base(int):
    """A stand-in Python type a result could have."""


class Reading(float):
    """A stand-in Python type outside the int family, which nothing in pyct enters."""


class Measured(float):
    """A stand-in tracked number outside the int family, as a tracked float will be."""

    expression: Expression

    @classmethod
    def made(cls, value: float, expression: Expression, sink: BranchSink) -> "Measured":
        made = cls(value)
        made.expression = expression
        return made


@pytest.fixture
def table(monkeypatch: pytest.MonkeyPatch) -> None:
    """A copy of the table for one test, so an entry made here is gone after it."""
    monkeypatch.setattr(numbers, "_TRACKED", dict(numbers._TRACKED))
    monkeypatch.setattr(numbers, "_CLASSES", set(numbers._CLASSES))


def test_a_result_is_tracked_by_the_class_its_own_type_entered() -> None:
    sink: list[SinkItem] = []

    number = numbers.tracked(3, ["+", "x", 1], sink)
    truth = numbers.tracked(True, [">", "x", 0], sink)
    real = numbers.tracked(2.5, ["/", "f", 2.0], sink)

    assert type(number) is ConcolicInt
    assert type(truth) is ConcolicBool
    assert type(real) is ConcolicFloat
    assert (number.expression, truth.expression) == (["+", "x", 1], [">", "x", 0])
    assert real.expression == ["/", "f", 2.0]
    assert number.sink is sink and real.sink is sink


def test_a_type_nothing_entered_fails_where_it_is_tracked() -> None:
    # a quietly plain value would lose the condition without a word; this names the gap
    with pytest.raises(LookupError, match="no tracked type is entered for Reading"):
        numbers.tracked(Reading(2.5), ["/", "x", 2], [])


@pytest.mark.usefixtures("table")
def test_a_type_enters_its_class_once() -> None:
    numbers.enter(Base, Tracked)
    numbers.enter(Base, Tracked)

    assert type(numbers.tracked(Base(4), "x", [])) is Tracked
    assert numbers.operand(Tracked.made(4, "x", [])) == "x"


@pytest.mark.usefixtures("table")
def test_a_second_class_for_a_type_is_refused() -> None:
    # two classes for one type would make the answer depend on which module Python read last
    with pytest.raises(ValueError, match="int is already tracked by ConcolicInt"):
        numbers.enter(int, Tracked)


@pytest.mark.usefixtures("table")
def test_an_int_reads_a_tracked_number_of_a_float_type_by_its_expression() -> None:
    # entered for a stand-in type, so a tracked float entered for float leaves this test alone
    numbers.enter(Reading, Measured)
    sink: list[SinkItem] = []
    x = ConcolicInt.made(5, expression="x", sink=sink)
    f = Measured.made(2.5, "f", sink)

    # int's own answers NotImplemented to a float, and float's mirrored operation answers, as
    # Python's does; the int keeps the condition on both sides
    less = x < f
    total = x + f

    assert numbers.operand(f) is None
    assert isinstance(less, ConcolicBool) and less.expression == ["<", "x", "f"]
    assert type(total) is ConcolicFloat and total.expression == ["+", "x", "f"]
    assert repr(total) == "7.5"
    assert sink == []


# a tracked int against a tracked float, both ways, and the answer Python gives on the plain
# values: 2**53 + 1 is no double, so an int read as a float first would answer the first two
# wrong, and CPython compares an int past 48 bits by calling the int's own methods
CROSSED: list[tuple[str, int, float, bool]] = [
    (">", 2**53 + 1, 2.0**53, True),
    ("==", 2**53 + 1, 2.0**53, False),
    ("<", -(2**53) - 1, -(2.0**53), True),
    ("<", 5, 2.5, False),
    (">=", 2, 2.5, False),
    ("!=", 3, 3.0, False),
]


@pytest.mark.parametrize(("op", "n", "f", "answer"), CROSSED, ids=[case[0] for case in CROSSED])
def test_a_tracked_int_meets_a_tracked_float_with_pythons_own_answer(
    op: str, n: int, f: float, answer: bool
) -> None:
    sink: list[SinkItem] = []
    x = ConcolicInt.made(n, expression="x", sink=sink)
    y = ConcolicFloat.made(f, expression="y", sink=sink)

    crossed = {">": x > y, "==": x == y, "<": x < y, ">=": x >= y, "!=": x != y}[op]
    mirrored = {">": y < x, "==": y == x, "<": y > x, ">=": y <= x, "!=": y != x}[op]

    assert isinstance(crossed, ConcolicBool) and isinstance(mirrored, ConcolicBool)
    assert crossed.expression == [op, "x", "y"]
    assert int.__bool__(crossed) is answer and int.__bool__(mirrored) is answer
    # float's own compare reads the int's plain value, so the int's own methods, which CPython
    # calls on an int past 48 bits, record no fork and no downgrade
    assert sink == []


def test_an_operand_reads_as_a_number_does() -> None:
    x = ConcolicInt.made(3, expression="x", sink=[])

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

    print(*(type(tracked(value, "x", [])).__name__ for value in (1, True, 1.5)))
    """
)


def test_the_table_is_full_whichever_core_module_is_imported_first() -> None:
    # this session has already imported every core module, so only a fresh interpreter shows
    # that pyct.core fills the table before a caller reaches numbers
    result = subprocess.run(
        [sys.executable, "-c", TABLE_ALONE], capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "ConcolicInt ConcolicBool ConcolicFloat\n"
